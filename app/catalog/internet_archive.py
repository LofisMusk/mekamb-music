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
_METADATA_URL = "https://archive.org/metadata/{identifier}"
_AUDIO_EXTENSIONS = (".mp3", ".flac", ".ogg", ".m4a", ".wav", ".wma", ".ape")
_MAX_METADATA_FETCHES = 25


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
            docs = json.loads(cached)
        else:
            docs = await self._fetch_with_retry(query, rows=rows)
            await self._redis.set(cache_key, json.dumps(docs), ex=self._cache_ttl_seconds)

        releases = _parse_docs(docs)
        return await self._with_audio_only_sizes(releases)

    async def _with_audio_only_sizes(
        self, releases: list[InternetArchiveRelease]
    ) -> list[InternetArchiveRelease]:
        """archive.org's `item_size` is the whole item (audio + cover art +
        per-track spectrogram PNGs + sqlite/xml metadata + the .torrent file
        itself), often 1.5-3x the actual audio content. Lidarr rejects releases
        that look oversized for their inferred quality tier, so an inflated size
        causes real, correctly-tracked albums to be silently dropped. Replace it
        with the sum of just the audio files."""
        limited = releases[:_MAX_METADATA_FETCHES]
        sizes = await asyncio.gather(
            *(self._audio_only_size(r.identifier) for r in limited), return_exceptions=True
        )
        resolved: list[InternetArchiveRelease] = []
        for release, size in zip(limited, sizes):
            if isinstance(size, Exception) or not size:
                resolved.append(release)
            else:
                resolved.append(
                    InternetArchiveRelease(
                        identifier=release.identifier,
                        title=release.title,
                        size_bytes=size,
                        downloads=release.downloads,
                        published_at=release.published_at,
                        torrent_url=release.torrent_url,
                    )
                )
        resolved.extend(releases[_MAX_METADATA_FETCHES:])
        return resolved

    async def _audio_only_size(self, identifier: str) -> int | None:
        cache_key = f"mekamb-music:ia-torznab:audio-size:{identifier}"
        cached = await self._redis.get(cache_key)
        if cached is not None:
            return int(cached)

        url = _METADATA_URL.format(identifier=identifier)
        try:
            async with httpx.AsyncClient(timeout=self._request_timeout_seconds) as client:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("internet-archive-metadata fetch failed for %s: %s", identifier, exc)
            return None

        files = payload.get("files", [])
        by_extension: dict[str, int] = {}
        for f in files:
            name = str(f.get("name") or "").lower()
            size = f.get("size")
            if not isinstance(size, (int, str)) or not str(size).isdigit():
                continue
            ext = next((e for e in _AUDIO_EXTENSIONS if name.endswith(e)), None)
            if ext is None:
                continue
            by_extension[ext] = by_extension.get(ext, 0) + int(size)

        if not by_extension:
            return None

        # Prefer mp3 (the format IA converts everything to and the one qBittorrent
        # ends up keeping after excluding duplicate formats); otherwise take
        # whichever single format has the most total bytes.
        total = by_extension.get(".mp3") or max(by_extension.values())
        await self._redis.set(cache_key, str(total), ex=self._cache_ttl_seconds * 24)
        return total

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
