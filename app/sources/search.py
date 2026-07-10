from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class UnifiedTorrentSearchItem:
    """Neutral shape for an external candidate. Retained so the recommendation
    engine's data model stays stable now that live torrent search is gone;
    external acquisition happens through Lidarr (see ``/catalog``)."""

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
