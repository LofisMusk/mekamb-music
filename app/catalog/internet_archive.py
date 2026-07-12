from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from redis.asyncio import Redis

logger = logging.getLogger("uvicorn.error")

_SEARCH_URL = "https://archive.org/advancedsearch.php"
_FIELDS = "identifier,title,mediatype,item_size,downloads,btih,publicdate"


@dataclass(frozen=True)
class InternetArchiveRelease:
    identifier: str
    title: str
    size_bytes: int
    downloads: int
    published_at: datetime
    torrent_url: str


class InternetArchiveClient:
    """Fetches "Archive BitTorrent"-format items from archive.org's own search
    API. archive.org's Elasticsearch backend is occasionally slow or briefly
    unavailable, and Prowlarr's built-in Cardigann definition gives up after a
    single ~100s timeout and then disables the indexer for hours. This client
    instead retries with backoff and caches successful responses in Redis so a
    transient archive.org hiccup never blocks a search or trips a downstream
    circuit breaker."""

    def __init__(
        self,
        *,
        redis_url: str,
        cache_ttl_seconds: int = 600,
        request_timeout_seconds: float = 25.0,
        max_attempts: int = 3,
    ) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._cache_ttl_seconds = cache_ttl_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._max_attempts = max_attempts

    async def search(self, query: str, *, rows: int = 100) -> list[InternetArchiveRelease]:
        cache_key = f"mekamb-music:ia-torznab:{query.strip().lower()}:{rows}"
        cached = await self._redis.get(cache_key)
        if cached is not None:
            return _parse_docs(json.loads(cached))

        docs = await self._fetch_with_retry(query, rows=rows)
        await self._redis.set(cache_key, json.dumps(docs), ex=self._cache_ttl_seconds)
        return _parse_docs(docs)

    async def _fetch_with_retry(self, query: str, *, rows: int) -> list[dict]:
        q = 'format:("Archive BitTorrent")'
        if query.strip():
            q = f"title:({query.strip()}) AND {q}"
        params = {
            "q": q,
            "fl[]": _FIELDS,
            "sort": "-publicdate",
            "rows": rows,
            "output": "json",
        }

        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self._request_timeout_seconds) as client:
                    response = await client.get(_SEARCH_URL, params=params)
                    response.raise_for_status()
                    payload = response.json()
                if "error" in payload:
                    raise InternetArchiveError(str(payload["error"]))
                return payload.get("response", {}).get("docs", [])
            except (httpx.HTTPError, InternetArchiveError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "internet-archive-search attempt %s/%s failed: %s",
                    attempt,
                    self._max_attempts,
                    exc,
                )
                if attempt < self._max_attempts:
                    await asyncio.sleep(1.5 * attempt)

        raise InternetArchiveError(f"archive.org search failed after {self._max_attempts} attempts") from last_error

    async def close(self) -> None:
        await self._redis.aclose()


class InternetArchiveError(RuntimeError):
    pass


def _parse_docs(docs: list[dict]) -> list[InternetArchiveRelease]:
    releases: list[InternetArchiveRelease] = []
    for doc in docs:
        identifier = str(doc.get("identifier") or "").strip()
        btih = str(doc.get("btih") or "").strip()
        if not identifier or not btih:
            continue
        published_at = _parse_date(doc.get("publicdate"))
        releases.append(
            InternetArchiveRelease(
                identifier=identifier,
                title=str(doc.get("title") or identifier).strip(),
                size_bytes=int(doc.get("item_size") or 0),
                downloads=int(doc.get("downloads") or 0),
                published_at=published_at,
                torrent_url=f"https://archive.org/download/{identifier}/{identifier}_archive.torrent",
            )
        )
    return releases


def _parse_date(raw: object) -> datetime:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
