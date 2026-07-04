from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, dataclass

from app.sources.personal_1337x import (
    Personal1337xProvider,
    Personal1337xSearchResult,
)
from app.sources.piratebay import PirateBayProvider, PirateBaySearchResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UnifiedTorrentSearchItem:
    source: str
    name: str
    torrent_id: str
    info_hash: str | None
    magnet_link: str | None
    source_url: str | None
    seeders: str
    leechers: str
    size: str | None
    size_bytes: int | None
    uploader: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class UnifiedTorrentSearch:
    def __init__(
        self,
        *,
        piratebay: PirateBayProvider,
        personal_1337x: Personal1337xProvider,
        variants_per_query: int = 3,
    ) -> None:
        self.piratebay = piratebay
        self.personal_1337x = personal_1337x
        self.variants_per_query = max(1, variants_per_query)

    async def search(self, query: str, *, redis=None) -> list[UnifiedTorrentSearchItem]:
        variants = music_query_variants(query)[: self.variants_per_query]
        if not variants:
            return []

        results: list[UnifiedTorrentSearchItem] = []
        for variant in variants:
            piratebay_items, thirteen_items = await asyncio.gather(
                self._search_piratebay(variant),
                self._search_1337x(variant, redis=redis),
            )
            if piratebay_items is not None:
                results.extend(piratebay_items)
            if thirteen_items is not None:
                results.extend(thirteen_items)

        return _top_seeded(_dedupe(results))

    async def _search_piratebay(self, query: str) -> list[UnifiedTorrentSearchItem] | None:
        try:
            return [_from_piratebay(item) for item in await self.piratebay.search(query)]
        except Exception as exc:
            logger.warning("Pirate Bay unified search failed for %r: %s", query, exc)
            return None

    async def _search_1337x(
        self,
        query: str,
        *,
        redis=None,
    ) -> list[UnifiedTorrentSearchItem] | None:
        try:
            items = await self.personal_1337x.search(
                query,
                page=1,
                sort_by="seeders",
                redis=redis,
            )
            return [_from_1337x(item) for item in items]
        except Exception as exc:
            logger.warning("1337x unified search failed for %r: %s", query, exc)
            return None


def music_query_variants(query: str) -> list[str]:
    normalized = _normalize_query(query)
    if not normalized:
        return []

    variants = [normalized]
    stripped = _strip_release_tags(normalized)
    if stripped and stripped != normalized:
        variants.append(stripped)

    separator_variant = re.sub(r"\s+[-–—]\s+", " ", stripped or normalized)
    if separator_variant and separator_variant not in variants:
        variants.append(separator_variant)

    compact_variant = re.sub(
        r"\b(album|single|ep|flac|mp3|lossless|official)\b",
        "",
        stripped,
        flags=re.I,
    )
    compact_variant = _normalize_query(compact_variant)
    if compact_variant and compact_variant not in variants:
        variants.append(compact_variant)

    return variants


def _from_piratebay(item: PirateBaySearchResult) -> UnifiedTorrentSearchItem:
    return UnifiedTorrentSearchItem(
        source="piratebay",
        name=item.name,
        torrent_id=item.torrent_id,
        info_hash=item.info_hash,
        magnet_link=item.magnet_link,
        source_url=item.url,
        seeders=item.seeders,
        leechers=item.leechers,
        size=None,
        size_bytes=item.size_bytes,
        uploader=item.uploader,
    )


def _from_1337x(item: Personal1337xSearchResult) -> UnifiedTorrentSearchItem:
    return UnifiedTorrentSearchItem(
        source="1337x",
        name=item.name,
        torrent_id=item.torrent_id,
        info_hash=None,
        magnet_link=None,
        source_url=item.url,
        seeders=item.seeders,
        leechers=item.leechers,
        size=item.size,
        size_bytes=None,
        uploader=item.uploader,
    )


def _dedupe(items: list[UnifiedTorrentSearchItem]) -> list[UnifiedTorrentSearchItem]:
    deduped: list[UnifiedTorrentSearchItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.source, item.torrent_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _top_seeded(items: list[UnifiedTorrentSearchItem]) -> list[UnifiedTorrentSearchItem]:
    return sorted(items, key=lambda item: _int(item.seeders), reverse=True)[:50]


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def _strip_release_tags(query: str) -> str:
    text = re.sub(
        r"[\[(][^\])]*(?:flac|mp3|320|lossless|vinyl|web|cd|remaster)[^\])]*[\])]",
        "",
        query,
        flags=re.I,
    )
    return _normalize_query(text)


def _int(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return 0
