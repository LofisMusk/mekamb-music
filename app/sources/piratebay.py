from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class PirateBaySourceError(RuntimeError):
    pass


class PirateBayMissingMetadata(RuntimeError):
    pass


@dataclass(frozen=True)
class PirateBaySearchResult:
    name: str
    torrent_id: str
    info_hash: str
    magnet_link: str
    url: str
    seeders: str
    leechers: str
    size_bytes: int
    num_files: int
    uploader: str
    category: str
    status: str
    added_at: datetime | None
    discovered_at: datetime

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["added_at"] = self.added_at.isoformat() if self.added_at else None
        data["discovered_at"] = self.discovered_at.isoformat()
        return data


@dataclass(frozen=True)
class PirateBayImportCandidate:
    torrent_id: str
    info_hash: str
    magnet_link: str
    uploader: str
    source_url: str
    name: str
    fetched_at: datetime


class PirateBayProvider:
    def __init__(
        self,
        *,
        api_base_url: str = "https://apibay.org",
        category: int = 100,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.category = category

    @classmethod
    def from_settings(cls, settings: object) -> "PirateBayProvider":
        return cls(
            api_base_url=getattr(settings, "piratebay_api_base_url", "https://apibay.org"),
            category=getattr(settings, "piratebay_category", 100),
        )

    async def search(self, query: str) -> list[PirateBaySearchResult]:
        query = query.strip()
        if not query:
            return []

        payload = await asyncio.to_thread(self._get_json, "/q.php", q=query, cat=str(self.category))
        if not isinstance(payload, list):
            raise PirateBaySourceError("Pirate Bay API returned an unexpected response.")

        now = datetime.now(UTC)
        return [_result for item in payload if (_result := self._parse_result(item, now))]

    async def resolve_for_import(self, torrent_id: str) -> PirateBayImportCandidate:
        torrent_id = torrent_id.strip()
        if not torrent_id:
            raise PirateBayMissingMetadata("Missing torrent id.")

        payload = await asyncio.to_thread(self._get_json, "/t.php", id=torrent_id)
        if not isinstance(payload, dict):
            raise PirateBaySourceError("Pirate Bay API returned an unexpected response.")

        result = self._parse_result(payload, datetime.now(UTC))
        if result is None:
            raise PirateBayMissingMetadata("Torrent metadata was not found.")

        return PirateBayImportCandidate(
            torrent_id=result.torrent_id,
            info_hash=result.info_hash,
            magnet_link=result.magnet_link,
            uploader=result.uploader,
            source_url=result.url,
            name=result.name,
            fetched_at=datetime.now(UTC),
        )

    def _get_json(self, path: str, **params: str) -> Any:
        url = f"{self.api_base_url}{path}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": _user_agent()})
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise PirateBaySourceError(f"Pirate Bay API returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            raise PirateBaySourceError(f"Could not reach Pirate Bay API: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise PirateBaySourceError("Pirate Bay API returned invalid JSON.") from exc

    def _parse_result(self, item: Any, discovered_at: datetime) -> PirateBaySearchResult | None:
        if not isinstance(item, dict):
            return None

        torrent_id = _string(item.get("id"))
        info_hash = _string(item.get("info_hash")).upper()
        name = _string(item.get("name"))
        if torrent_id in {"", "0"} or not name or info_hash in {"", "0" * 40}:
            return None

        return PirateBaySearchResult(
            name=name,
            torrent_id=torrent_id,
            info_hash=info_hash,
            magnet_link=_magnet_link(info_hash=info_hash, name=name),
            url=f"https://thepiratebay.org/description.php?id={quote(torrent_id)}",
            seeders=_string(item.get("seeders"), "0"),
            leechers=_string(item.get("leechers"), "0"),
            size_bytes=_integer(item.get("size")),
            num_files=_integer(item.get("num_files")),
            uploader=_string(item.get("username"), "unknown"),
            category=_string(item.get("category")),
            status=_string(item.get("status")),
            added_at=_timestamp(item.get("added")),
            discovered_at=discovered_at,
        )

def _magnet_link(*, info_hash: str, name: str) -> str:
    trackers = [
        "udp://tracker.opentrackr.org:1337/announce",
        "udp://open.stealth.si:80/announce",
        "udp://tracker.torrent.eu.org:451/announce",
        "udp://tracker.bittor.pw:1337/announce",
        "udp://public.popcorn-tracker.org:6969/announce",
    ]
    tracker_params = "".join(f"&tr={quote(tracker, safe='')}" for tracker in trackers)
    return f"magnet:?xt=urn:btih:{info_hash}&dn={quote(name)}{tracker_params}"


def _timestamp(value: object) -> datetime | None:
    timestamp = _integer(value)
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)


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
