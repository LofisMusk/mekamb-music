from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class MissingTorrentMetadata(RuntimeError):
    pass


class SourceBlockedError(RuntimeError):
    pass


class Py1337xLike(Protocol):
    base_url: str

    def search(
        self,
        query: str,
        page: int = 1,
        category: str | None = None,
        sort_by: str | None = None,
        order: str = "desc",
    ) -> Any:
        ...

    def info(self, link: str | None = None, torrent_id: str | None = None) -> Any:
        ...


@dataclass(frozen=True)
class Personal1337xSearchResult:
    name: str
    torrent_id: str
    url: str
    seeders: str
    leechers: str
    size: str
    time: str
    uploader: str
    uploader_link: str
    discovered_at: datetime

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["discovered_at"] = self.discovered_at.isoformat()
        return data


@dataclass(frozen=True)
class Personal1337xImportCandidate:
    torrent_id: str
    info_hash: str
    magnet_link: str
    uploader: str
    source_url: str
    name: str | None
    fetched_at: datetime


def _get_attr(item: object, name: str, default: str = "") -> str:
    value = getattr(item, name, default)
    if value is None:
        return default
    return str(value)


def _music_category() -> str:
    try:
        from py1337x.types import category
    except Exception:
        return "Music"
    return str(getattr(category, "MUSIC", "Music"))


def _seeders_sort() -> str:
    try:
        from py1337x.types import sort
    except Exception:
        return "seeders"
    return str(getattr(sort, "SEEDERS", "seeders"))


def _split_base_urls(raw: str) -> list[str]:
    return [part.strip() for part in raw.replace("\n", ",").split(",") if part.strip()]


def _normalize_base_urls(base_urls: list[str] | tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for base_url in base_urls:
        value = base_url.strip().rstrip("/")
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized or ["https://1337x.to"]


def _build_default_client(base_url: str) -> Py1337xLike:
    from py1337x import Py1337x

    return Py1337x(base_url=base_url)


class Personal1337xProvider:
    def __init__(
        self,
        *,
        base_url: str = "https://1337x.to",
        base_urls: list[str] | tuple[str, ...] | None = None,
        max_pages: int = 1,
        client: Py1337xLike | None = None,
        category: str | None = None,
        search_cache_ttl: int = 300,
    ) -> None:
        self.base_urls = _normalize_base_urls(base_urls or [base_url])
        self.base_url = self.base_urls[0]
        self.max_pages = max(1, max_pages)
        self._client = client
        self._clients: dict[str, Py1337xLike] = {}
        self._category = category or _music_category()
        self._search_cache_ttl = search_cache_ttl

    @classmethod
    def from_settings(cls, settings: object) -> "Personal1337xProvider":
        base_url = getattr(settings, "personal_1337x_base_url", "https://1337x.to")
        configured_base_urls = _split_base_urls(
            getattr(settings, "personal_1337x_base_urls", "")
        )
        return cls(
            base_url=base_url,
            base_urls=configured_base_urls or [base_url],
            max_pages=getattr(settings, "personal_1337x_max_pages", 1),
            search_cache_ttl=getattr(settings, "search_cache_ttl_seconds", 300),
        )

    @property
    def client(self) -> Py1337xLike:
        return self._client_for(self.base_url)

    def _client_for(self, base_url: str) -> Py1337xLike:
        if self._client is not None and base_url == self.base_url:
            return self._client
        if base_url not in self._clients:
            self._clients[base_url] = _build_default_client(base_url)
        return self._clients[base_url]

    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        sort_by: str | None = None,
        redis=None,
    ) -> list[Personal1337xSearchResult]:
        if page > self.max_pages:
            return []

        # Redis cache
        cache_key = f"1337x:search:{query}:{page}:{sort_by or 'seeders'}"
        if redis is not None:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    logger.debug("Search cache hit: %s", cache_key)
                    return _deserialize_results(cached)
            except Exception as exc:
                logger.warning("Redis get failed (ignored): %s", exc)

        selected_sort = _seeders_sort() if sort_by in (None, "seeders") else sort_by
        last_blocked_error: SourceBlockedError | None = None
        last_search_error: Exception | None = None

        for base_url in self.base_urls:
            try:
                result = await asyncio.to_thread(
                    self._client_for(base_url).search,
                    query,
                    page=page,
                    category=self._category,
                    sort_by=selected_sort,
                    order="desc",
                )
            except Exception as exc:
                logger.warning("1337x search failed for %s: %s", base_url, exc)
                last_search_error = exc
                continue

            results = self._search_results_from_response(result)
            if results:
                if redis is not None:
                    try:
                        await redis.setex(cache_key, self._search_cache_ttl, _serialize_results(results))
                        logger.debug("Search cache set: %s (TTL=%ds)", cache_key, self._search_cache_ttl)
                    except Exception as exc:
                        logger.warning("Redis set failed (ignored): %s", exc)
                return results

            try:
                await asyncio.to_thread(self._raise_if_search_is_blocked, base_url, query)
            except SourceBlockedError as exc:
                logger.warning("1337x mirror blocked for %s: %s", base_url, exc)
                last_blocked_error = exc
                continue

            return []

        if last_blocked_error is not None:
            raise SourceBlockedError(
                "All configured 1337x mirrors are returning a Cloudflare challenge to the backend."
            ) from last_blocked_error
        if last_search_error is not None:
            raise last_search_error
        return []

    async def resolve_for_import(self, torrent_id: str) -> Personal1337xImportCandidate:
        torrent_id = torrent_id.strip()
        if not torrent_id:
            raise MissingTorrentMetadata("Missing torrent id.")

        last_error: Exception | None = None
        for base_url in self.base_urls:
            try:
                info = await asyncio.to_thread(self._client_for(base_url).info, torrent_id=torrent_id)
            except Exception as exc:
                logger.warning("1337x info lookup failed for %s: %s", base_url, exc)
                last_error = exc
                continue

            magnet_link = _get_attr(info, "magnet_link")
            info_hash = _get_attr(info, "info_hash")
            if magnet_link and info_hash:
                return Personal1337xImportCandidate(
                    torrent_id=torrent_id,
                    info_hash=info_hash,
                    magnet_link=magnet_link,
                    uploader=_get_attr(info, "uploader"),
                    source_url=self._source_url(info, torrent_id, base_url),
                    name=_get_attr(info, "name") or None,
                    fetched_at=datetime.now(UTC),
                )

            last_error = MissingTorrentMetadata(
                "Torrent has no magnet link." if not magnet_link else "Torrent has no info hash."
            )

        if last_error is not None:
            raise last_error
        raise MissingTorrentMetadata("Missing torrent metadata.")

    def _search_results_from_response(self, result: object) -> list[Personal1337xSearchResult]:
        now = datetime.now(UTC)
        results: list[Personal1337xSearchResult] = []
        for item in getattr(result, "items", []):
            results.append(
                Personal1337xSearchResult(
                    name=_get_attr(item, "name"),
                    torrent_id=_get_attr(item, "torrent_id"),
                    url=_get_attr(item, "url"),
                    seeders=_get_attr(item, "seeders"),
                    leechers=_get_attr(item, "leechers"),
                    size=_get_attr(item, "size"),
                    time=_get_attr(item, "time"),
                    uploader=_get_attr(item, "uploader"),
                    uploader_link=_get_attr(item, "uploader_link"),
                    discovered_at=now,
                )
            )
        return results

    def _raise_if_search_is_blocked(self, base_url: str, query: str) -> None:
        url = f"{base_url}/search/{quote(query)}/1/"
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
                )
            },
        )
        try:
            with urlopen(request, timeout=12) as response:
                body = response.read(4096).decode("utf-8", errors="replace")
        except HTTPError as exc:
            body = exc.read(4096).decode("utf-8", errors="replace")
            if exc.code in {403, 429} and _looks_like_cloudflare_challenge(body):
                raise SourceBlockedError(
                    f"{base_url} is returning a Cloudflare challenge to the backend."
                ) from exc
            return
        except URLError:
            return

        if _looks_like_cloudflare_challenge(body):
            raise SourceBlockedError(
                f"{base_url} is returning a Cloudflare challenge to the backend."
            )

    def _source_url(self, info: object, torrent_id: str, base_url: str) -> str:
        for attr in ("url", "link", "source_url"):
            value = _get_attr(info, attr)
            if value:
                return value
        return f"{base_url}/torrent/{torrent_id}/"


def _serialize_results(results: list[Personal1337xSearchResult]) -> str:
    return json.dumps([r.to_dict() for r in results])


def _deserialize_results(raw: str) -> list[Personal1337xSearchResult]:
    items = json.loads(raw)
    return [
        Personal1337xSearchResult(
            **{**item, "discovered_at": datetime.fromisoformat(item["discovered_at"])}
        )
        for item in items
    ]


def _looks_like_cloudflare_challenge(body: str) -> bool:
    lowered = body.lower()
    return "just a moment" in lowered and "cloudflare" in lowered
