from __future__ import annotations

import asyncio
import base64
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


class MusicIndexerSourceError(RuntimeError):
    pass


class MusicIndexerMissingMetadata(RuntimeError):
    pass


@dataclass(frozen=True)
class MusicIndexerSearchResult:
    source: str
    name: str
    torrent_id: str
    info_hash: str
    magnet_link: str
    url: str
    seeders: str
    leechers: str
    size_bytes: int
    uploader: str
    discovered_at: datetime

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["discovered_at"] = self.discovered_at.isoformat()
        return data


@dataclass(frozen=True)
class MusicIndexerImportCandidate:
    torrent_id: str
    info_hash: str
    magnet_link: str
    uploader: str
    source_url: str
    name: str
    fetched_at: datetime


class MusicIndexerProvider:
    def __init__(
        self,
        *,
        torznab_urls: list[str] | tuple[str, ...] | None = None,
        api_key: str = "",
        categories: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.torznab_urls = _normalize_urls(torznab_urls or [])
        self.api_key = api_key.strip()
        self.categories = [category.strip() for category in categories or ["3000"] if category.strip()]

    @classmethod
    def from_settings(cls, settings: object) -> "MusicIndexerProvider":
        return cls(
            torznab_urls=_split(getattr(settings, "music_indexer_torznab_urls", "")),
            api_key=getattr(settings, "music_indexer_api_key", ""),
            categories=_split(getattr(settings, "music_indexer_categories", "3000")),
        )

    async def search(self, query: str) -> list[MusicIndexerSearchResult]:
        query = query.strip()
        if not query or not self.torznab_urls:
            return []

        results: list[MusicIndexerSearchResult] = []
        last_error: Exception | None = None
        for url in self.torznab_urls:
            try:
                payload = await asyncio.to_thread(self._fetch, url, query)
            except Exception as exc:
                last_error = exc
                continue
            results.extend(_parse_torznab_results(payload, source_url=url))

        if not results and last_error is not None:
            raise MusicIndexerSourceError(f"Music indexer search failed: {last_error}") from last_error
        return _dedupe(results)

    def candidate_from_result(self, result: MusicIndexerSearchResult) -> MusicIndexerImportCandidate:
        return MusicIndexerImportCandidate(
            torrent_id=result.torrent_id,
            info_hash=result.info_hash,
            magnet_link=result.magnet_link,
            uploader=result.uploader,
            source_url=result.url,
            name=result.name,
            fetched_at=datetime.now(UTC),
        )

    def candidate_from_payload(self, payload: dict[str, Any]) -> MusicIndexerImportCandidate:
        name = _string(payload.get("name"))
        magnet_link = _string(payload.get("magnet_link"))
        info_hash = _string(payload.get("info_hash")).upper() or _info_hash_from_magnet(magnet_link)
        torrent_id = _string(payload.get("torrent_id")) or info_hash
        if not name:
            raise MusicIndexerMissingMetadata("Indexer import is missing a title.")
        if not magnet_link:
            raise MusicIndexerMissingMetadata("Indexer import is missing a magnet link.")
        if not info_hash:
            raise MusicIndexerMissingMetadata("Indexer import is missing an info hash.")

        return MusicIndexerImportCandidate(
            torrent_id=torrent_id,
            info_hash=info_hash,
            magnet_link=magnet_link,
            uploader=_string(payload.get("uploader"), "indexer"),
            source_url=_string(payload.get("source_url"), "indexer"),
            name=name,
            fetched_at=datetime.now(UTC),
        )

    def _fetch(self, base_url: str, query: str) -> str:
        params = {
            "t": "search",
            "q": query,
            "cat": ",".join(self.categories),
        }
        if self.api_key:
            params["apikey"] = self.api_key
        separator = "&" if "?" in base_url else "?"
        url = f"{base_url}{separator}{urlencode(params)}"
        request = Request(url, headers={"User-Agent": _user_agent()})
        try:
            with urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise MusicIndexerSourceError(f"Indexer returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            raise MusicIndexerSourceError(f"Could not reach indexer: {exc}") from exc


def _parse_torznab_results(payload: str, *, source_url: str) -> list[MusicIndexerSearchResult]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise MusicIndexerSourceError("Indexer returned invalid XML.") from exc

    now = datetime.now(UTC)
    results: list[MusicIndexerSearchResult] = []
    for item in root.findall(".//channel/item"):
        attrs = _torznab_attrs(item)
        title = _text(item, "title")
        magnet_link = attrs.get("magneturl") or _enclosure_url(item) or _text(item, "link")
        if not magnet_link.startswith("magnet:"):
            continue
        info_hash = (attrs.get("infohash") or _info_hash_from_magnet(magnet_link)).upper()
        if not title or not info_hash:
            continue

        results.append(
            MusicIndexerSearchResult(
                source="indexer",
                name=title,
                torrent_id=info_hash,
                info_hash=info_hash,
                magnet_link=magnet_link,
                url=_text(item, "guid") or _text(item, "link") or source_url,
                seeders=attrs.get("seeders") or "0",
                leechers=attrs.get("leechers") or attrs.get("peers") or "0",
                size_bytes=_integer(_text(item, "size") or _enclosure_length(item)),
                uploader=attrs.get("poster") or attrs.get("author") or "indexer",
                discovered_at=now,
            )
        )
    return results


def _torznab_attrs(item: ElementTree.Element) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for child in item:
        if _local_name(child.tag) != "attr":
            continue
        name = child.attrib.get("name", "").strip().lower()
        value = child.attrib.get("value", "").strip()
        if name and value:
            attrs[name] = value
    return attrs


def _text(item: ElementTree.Element, name: str) -> str:
    for child in item:
        if _local_name(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def _enclosure_url(item: ElementTree.Element) -> str:
    for child in item:
        if _local_name(child.tag) == "enclosure":
            return child.attrib.get("url", "").strip()
    return ""


def _enclosure_length(item: ElementTree.Element) -> str:
    for child in item:
        if _local_name(child.tag) == "enclosure":
            return child.attrib.get("length", "").strip()
    return ""


def _info_hash_from_magnet(magnet_link: str) -> str:
    parsed = urlparse(magnet_link)
    xt_values = parse_qs(parsed.query).get("xt", [])
    for value in xt_values:
        if value.lower().startswith("urn:btih:"):
            token = value.rsplit(":", 1)[-1].strip()
            if len(token) == 32:
                try:
                    return base64.b32decode(token.upper()).hex().upper()
                except Exception:
                    return ""
            return token.upper()
    return ""


def _dedupe(results: list[MusicIndexerSearchResult]) -> list[MusicIndexerSearchResult]:
    deduped: list[MusicIndexerSearchResult] = []
    seen: set[str] = set()
    for item in results:
        if item.info_hash in seen:
            continue
        seen.add(item.info_hash)
        deduped.append(item)
    return deduped


def _normalize_urls(urls: list[str] | tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for url in urls:
        value = url.strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _split(raw: str) -> list[str]:
    return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _integer(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _string(value: object, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _user_agent() -> str:
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
