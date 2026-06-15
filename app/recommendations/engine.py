from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ImportJob, LikedTrack, Track, TrackPlay
from app.sources.indexers import MusicIndexerProvider
from app.sources.personal_1337x import Personal1337xProvider
from app.sources.piratebay import PirateBayProvider
from app.sources.search import UnifiedTorrentSearchItem, music_query_variants

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocalTrackRecommendation:
    track: Track
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class ExternalRecommendation:
    item: UnifiedTorrentSearchItem
    score: float
    query: str
    reasons: list[str]
    already_in_library: bool


@dataclass(frozen=True)
class RecommendationSet:
    seed_track: Track | None
    local_tracks: list[LocalTrackRecommendation]
    external_candidates: list[ExternalRecommendation]


class RecommendationEngine:
    def __init__(
        self,
        *,
        session: AsyncSession,
        piratebay: PirateBayProvider,
        personal_1337x: Personal1337xProvider,
        indexer: MusicIndexerProvider,
    ) -> None:
        self.session = session
        self.piratebay = piratebay
        self.personal_1337x = personal_1337x
        self.indexer = indexer

    async def recommend_for_track(
        self,
        track_id: UUID,
        *,
        local_limit: int,
        external_limit: int,
        sources: list[str],
    ) -> RecommendationSet:
        seed = await self.session.get(Track, track_id)
        if seed is None:
            raise LookupError(f"Track {track_id} not found.")

        local = await self._local_recommendations_for_seed(seed, limit=local_limit)
        external = await self._external_candidates_for_queries(
            self._queries_for_seed(seed),
            sources=sources,
            limit=external_limit,
            preferred_artist=seed.artist,
            preferred_album=seed.album,
        )
        return RecommendationSet(seed_track=seed, local_tracks=local, external_candidates=external)

    async def recommend_for_library(
        self,
        *,
        local_limit: int,
        external_limit: int,
        sources: list[str],
    ) -> RecommendationSet:
        seed_tracks = await self._library_seed_tracks(limit=8)
        local = await self._local_recommendations_for_library(seed_tracks, limit=local_limit)
        queries: list[str] = []
        for track in seed_tracks:
            queries.extend(self._queries_for_seed(track))
        external = await self._external_candidates_for_queries(
            _dedupe_text(queries),
            sources=sources,
            limit=external_limit,
            preferred_artist=None,
            preferred_album=None,
        )
        return RecommendationSet(seed_track=seed_tracks[0] if seed_tracks else None, local_tracks=local, external_candidates=external)

    async def _library_seed_tracks(self, *, limit: int) -> list[Track]:
        liked_rows = await self.session.scalars(
            select(Track)
            .join(LikedTrack, LikedTrack.track_id == Track.id)
            .order_by(LikedTrack.created_at.desc())
            .limit(limit)
        )
        seeds = list(liked_rows)
        if len(seeds) >= limit:
            return seeds

        recent_rows = await self.session.scalars(
            select(Track)
            .join(TrackPlay, TrackPlay.track_id == Track.id)
            .group_by(Track.id)
            .order_by(func.max(TrackPlay.played_at).desc())
            .limit(limit)
        )
        by_id = {track.id: track for track in seeds}
        for track in recent_rows:
            by_id.setdefault(track.id, track)
        if by_id:
            return list(by_id.values())[:limit]

        fallback = await self.session.scalars(select(Track).order_by(Track.created_at.desc()).limit(limit))
        return list(fallback)

    async def _local_recommendations_for_seed(
        self,
        seed: Track,
        *,
        limit: int,
    ) -> list[LocalTrackRecommendation]:
        tracks = list(await self.session.scalars(select(Track).where(Track.id != seed.id)))
        scored = [_score_track_against_seed(seed, candidate) for candidate in tracks]
        return sorted(
            [item for item in scored if item.score > 0],
            key=lambda item: item.score,
            reverse=True,
        )[:limit]

    async def _local_recommendations_for_library(
        self,
        seed_tracks: list[Track],
        *,
        limit: int,
    ) -> list[LocalTrackRecommendation]:
        if not seed_tracks:
            return []
        seed_ids = {track.id for track in seed_tracks}
        candidates = list(await self.session.scalars(select(Track).where(Track.id.not_in(seed_ids))))
        best: dict[UUID, LocalTrackRecommendation] = {}
        for seed in seed_tracks:
            for candidate in candidates:
                scored = _score_track_against_seed(seed, candidate)
                current = best.get(candidate.id)
                if scored.score > 0 and (current is None or scored.score > current.score):
                    best[candidate.id] = scored
        return sorted(best.values(), key=lambda item: item.score, reverse=True)[:limit]

    async def _external_candidates_for_queries(
        self,
        queries: list[str],
        *,
        sources: list[str],
        limit: int,
        preferred_artist: str | None,
        preferred_album: str | None,
    ) -> list[ExternalRecommendation]:
        if limit <= 0:
            return []

        library_fingerprint = await self._library_fingerprint()
        imported_hashes = await self._imported_info_hashes()
        candidates: list[ExternalRecommendation] = []
        for query in _dedupe_text(queries)[:8]:
            items = await self._search_sources(query, sources=sources)
            for item in items:
                already = _already_in_library(item, library_fingerprint, imported_hashes)
                score, reasons = _score_external_item(
                    item,
                    query=query,
                    preferred_artist=preferred_artist,
                    preferred_album=preferred_album,
                    already_in_library=already,
                )
                candidates.append(
                    ExternalRecommendation(
                        item=item,
                        score=score,
                        query=query,
                        reasons=reasons,
                        already_in_library=already,
                    )
                )

        return sorted(
            _dedupe_external(candidates),
            key=lambda candidate: candidate.score,
            reverse=True,
        )[:limit]

    async def _search_sources(
        self,
        query: str,
        *,
        sources: list[str],
    ) -> list[UnifiedTorrentSearchItem]:
        normalized_sources = {source.strip().lower() for source in sources}
        results: list[UnifiedTorrentSearchItem] = []
        if "indexer" in normalized_sources:
            try:
                results.extend(_from_indexer(item) for item in await self.indexer.search(query))
            except Exception as exc:
                logger.warning("Recommendation indexer search failed for %r: %s", query, exc)
        if "piratebay" in normalized_sources:
            try:
                results.extend(_from_piratebay(item) for item in await self.piratebay.search(query))
            except Exception as exc:
                logger.warning("Recommendation Pirate Bay search failed for %r: %s", query, exc)
        if "1337x" in normalized_sources:
            try:
                results.extend(_from_1337x(item) for item in await self.personal_1337x.search(query, page=1, sort_by="seeders"))
            except Exception as exc:
                logger.warning("Recommendation 1337x search failed for %r: %s", query, exc)
        return results

    async def _library_fingerprint(self) -> set[frozenset[str]]:
        tracks = await self.session.scalars(select(Track))
        fingerprints: set[frozenset[str]] = set()
        for track in tracks:
            fingerprints.update(_track_fingerprints(track))
        return fingerprints

    async def _imported_info_hashes(self) -> set[str]:
        hashes = await self.session.scalars(select(ImportJob.info_hash))
        return {str(info_hash).upper() for info_hash in hashes if info_hash}

    def _queries_for_seed(self, track: Track) -> list[str]:
        queries: list[str] = []
        artist = _clean_text(track.artist)
        title = _clean_text(track.title)
        album = _clean_text(track.album)
        if artist and title:
            queries.append(f"{artist} {title}")
        if artist and album:
            queries.append(f"{artist} {album}")
        if artist:
            queries.append(f"{artist} album")
        expanded: list[str] = []
        for query in queries:
            expanded.extend(music_query_variants(query))
        return _dedupe_text(expanded)


def _score_track_against_seed(seed: Track, candidate: Track) -> LocalTrackRecommendation:
    score = 0.0
    reasons: list[str] = []

    if _same_text(seed.artist, candidate.artist) and seed.artist:
        score += 55.0
        reasons.append("same_artist")
    if _same_text(seed.album, candidate.album) and seed.album:
        score += 35.0
        reasons.append("same_album")

    overlap = _token_overlap(
        f"{seed.artist or ''} {seed.album or ''} {seed.title}",
        f"{candidate.artist or ''} {candidate.album or ''} {candidate.title}",
    )
    if overlap:
        score += min(25.0, overlap * 6.0)
        reasons.append("metadata_overlap")

    if seed.duration_seconds and candidate.duration_seconds:
        diff = abs(seed.duration_seconds - candidate.duration_seconds)
        if diff <= 30:
            score += 10.0
            reasons.append("similar_duration")
        elif diff <= 90:
            score += 4.0
            reasons.append("near_duration")

    return LocalTrackRecommendation(track=candidate, score=round(score, 2), reasons=reasons)


def _score_external_item(
    item: UnifiedTorrentSearchItem,
    *,
    query: str,
    preferred_artist: str | None,
    preferred_album: str | None,
    already_in_library: bool,
) -> tuple[float, list[str]]:
    score = float(_int(item.seeders))
    reasons = ["seeders"]
    name = item.name.lower()

    if preferred_artist and _clean_text(preferred_artist).lower() in name:
        score += 40.0
        reasons.append("artist_match")
    if preferred_album and _clean_text(preferred_album).lower() in name:
        score += 25.0
        reasons.append("album_match")
    query_overlap = _token_overlap(query, item.name)
    if query_overlap:
        score += min(30.0, query_overlap * 8.0)
        reasons.append("query_overlap")
    if item.source == "indexer":
        score += 20.0
        reasons.append("configured_indexer")
    if already_in_library:
        score -= 1000.0
        reasons.append("already_in_library")
    return round(score, 2), reasons


def _from_indexer(item: object) -> UnifiedTorrentSearchItem:
    return UnifiedTorrentSearchItem(
        source="indexer",
        name=getattr(item, "name"),
        torrent_id=getattr(item, "torrent_id"),
        info_hash=getattr(item, "info_hash"),
        magnet_link=getattr(item, "magnet_link"),
        source_url=getattr(item, "url"),
        seeders=getattr(item, "seeders"),
        leechers=getattr(item, "leechers"),
        size=None,
        size_bytes=getattr(item, "size_bytes"),
        uploader=getattr(item, "uploader"),
    )


def _from_piratebay(item: object) -> UnifiedTorrentSearchItem:
    return UnifiedTorrentSearchItem(
        source="piratebay",
        name=getattr(item, "name"),
        torrent_id=getattr(item, "torrent_id"),
        info_hash=getattr(item, "info_hash"),
        magnet_link=getattr(item, "magnet_link"),
        source_url=getattr(item, "url"),
        seeders=getattr(item, "seeders"),
        leechers=getattr(item, "leechers"),
        size=None,
        size_bytes=getattr(item, "size_bytes"),
        uploader=getattr(item, "uploader"),
    )


def _from_1337x(item: object) -> UnifiedTorrentSearchItem:
    return UnifiedTorrentSearchItem(
        source="1337x",
        name=getattr(item, "name"),
        torrent_id=getattr(item, "torrent_id"),
        info_hash=None,
        magnet_link=None,
        source_url=getattr(item, "url"),
        seeders=getattr(item, "seeders"),
        leechers=getattr(item, "leechers"),
        size=getattr(item, "size"),
        size_bytes=None,
        uploader=getattr(item, "uploader"),
    )


def _already_in_library(
    item: UnifiedTorrentSearchItem,
    library_fingerprint: set[frozenset[str]],
    imported_hashes: set[str],
) -> bool:
    if item.info_hash and item.info_hash.upper() in imported_hashes:
        return True
    item_tokens = _tokens(item.name)
    if not item_tokens:
        return False
    return any(fingerprint and fingerprint.issubset(item_tokens) for fingerprint in library_fingerprint)


def _track_fingerprints(track: Track) -> set[frozenset[str]]:
    values = [
        f"{track.artist or ''} {track.title}",
        f"{track.artist or ''} {track.album or ''}",
        track.title,
        track.album or "",
        track.original_filename,
    ]
    return {frozenset(_tokens(value)) for value in values if _tokens(value)}


def _dedupe_external(items: list[ExternalRecommendation]) -> list[ExternalRecommendation]:
    best: dict[tuple[str, str], ExternalRecommendation] = {}
    for item in items:
        key = (item.item.source, item.item.info_hash or item.item.torrent_id or item.item.name)
        current = best.get(key)
        if current is None or item.score > current.score:
            best[key] = item
    return list(best.values())


def _dedupe_text(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        key = text.lower()
        if text and key not in seen:
            deduped.append(text)
            seen.add(key)
    return deduped


def _same_text(left: str | None, right: str | None) -> bool:
    return bool(left and right and _clean_text(left).lower() == _clean_text(right).lower())


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _token_overlap(left: str, right: str) -> int:
    return len(_tokens(left) & _tokens(right))


def _tokens(value: str) -> set[str]:
    stop = {"the", "a", "an", "and", "or", "feat", "ft", "official", "audio", "video"}
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", value.lower())
        if len(token) > 2 and token not in stop
    }


def _int(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return 0
