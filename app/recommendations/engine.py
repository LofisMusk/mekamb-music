from __future__ import annotations

import logging
import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DEFAULT_API_KEY_ID
from app.core.config import settings
from app.db.models import (
    ImportJob,
    LikedTrack,
    PersonalizationSignal,
    Track,
    TrackAudioFeature,
    TrackNeighbor,
    TrackPlay,
)
from app.recommendations.gemini import (
    GeminiCandidate,
    GeminiRecommendationClient,
    GeminiRecommendationUnavailable,
)
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


@dataclass(frozen=True)
class DailyMix:
    id: str
    title: str
    description: str
    seed_label: str
    tracks: list[LocalTrackRecommendation]


@dataclass(frozen=True)
class PersonalizedHome:
    recommended_tracks: list[LocalTrackRecommendation]
    daily_mixes: list[DailyMix]


@dataclass
class PersonalizationProfile:
    track_weights: dict[UUID, float]
    artist_weights: dict[str, float]
    album_weights: dict[str, float]
    token_weights: dict[str, float]
    seed_labels: list[str]


class RecommendationEngine:
    def __init__(
        self,
        *,
        session: AsyncSession,
        api_key_id: str = DEFAULT_API_KEY_ID,
        gemini_client: GeminiRecommendationClient | None = None,
        redis=None,
    ) -> None:
        self.session = session
        self.api_key_id = api_key_id
        self.gemini_client = gemini_client
        self.redis = redis

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

    async def personalized_home(
        self,
        *,
        local_limit: int,
        mix_count: int,
        mix_size: int,
    ) -> PersonalizedHome:
        tracks = list(
            await self.session.scalars(
                select(Track)
                .order_by(Track.last_accessed.desc())
                .limit(settings.recommendation_scan_limit)
            )
        )
        if not tracks:
            return PersonalizedHome(recommended_tracks=[], daily_mixes=[])

        profile = await self._personalization_profile()
        day = date.today().isoformat()
        scored = _score_personalized_tracks(tracks, profile=profile, day=day, salt="home")
        recommended = _diversify_recommendations(scored, limit=local_limit)
        mixes = _build_daily_mixes(
            tracks,
            profile=profile,
            day=day,
            mix_count=mix_count,
            mix_size=mix_size,
        )
        return PersonalizedHome(recommended_tracks=recommended, daily_mixes=mixes)

    async def autoplay_queue(
        self,
        seed_track_id: UUID,
        *,
        exclude_track_ids: set[UUID],
        limit: int,
    ) -> list[LocalTrackRecommendation]:
        """Radio-style continuation for when the playback queue runs out.

        Local tracks only — no external torrent candidates — ordered for continuous
        listening: seed similarity plus the personalization profile, capped per artist so
        the radio doesn't collapse into one artist's discography. Tracks the client already
        has queued (exclude_track_ids) and tracks played in the last few hours are skipped
        so the continuation doesn't replay what the listener just heard.
        """
        seed = await self.session.get(Track, seed_track_id)
        if seed is None:
            raise LookupError(f"Track {seed_track_id} not found.")

        excluded = {seed.id, *exclude_track_ids, *await self._recently_played_track_ids()}
        candidates = list(
            await self.session.scalars(
                select(Track)
                .where(Track.id.not_in(excluded))
                .order_by(Track.last_accessed.desc())
                .limit(settings.recommendation_scan_limit)
            )
        )
        if not candidates:
            return []

        features = await self._features_by_track_ids([seed.id, *(track.id for track in candidates)])
        profile = await self._personalization_profile()
        neighbors = await self._collaborative_neighbors(seed.id, [c.id for c in candidates])
        scored = [
            _score_track_against_seed(
                seed,
                candidate,
                seed_feature=features.get(seed.id),
                candidate_feature=features.get(candidate.id),
                profile=profile,
                collaborative_neighbor=neighbors.get(candidate.id),
            )
            for candidate in candidates
        ]
        ranked = sorted(scored, key=lambda item: item.score, reverse=True)
        # Unlike one-shot recommendations, radio must keep playing even when nothing
        # scores positively (tiny library, no metadata overlap) — so no score>0 filter.
        if settings.recommendation_sequencing_enabled:
            return _sequence_autoplay_batch(
                ranked,
                limit=limit,
                features_by_track_id=features,
                profile=profile,
                max_per_artist=3,
            )
        return _diversify_recommendations(ranked, limit=limit, max_per_artist=3)

    async def _recently_played_track_ids(self, *, hours: int = 3) -> set[UUID]:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        rows = await self.session.scalars(
            select(TrackPlay.track_id)
            .where(TrackPlay.api_key_id == self.api_key_id)
            .where(TrackPlay.played_at >= cutoff)
            .limit(200)
        )
        return set(rows)

    async def _library_seed_tracks(self, *, limit: int) -> list[Track]:
        liked_rows = await self.session.scalars(
            select(Track)
            .join(LikedTrack, LikedTrack.track_id == Track.id)
            .where(LikedTrack.api_key_id == self.api_key_id)
            .order_by(LikedTrack.created_at.desc())
            .limit(limit)
        )
        seeds = list(liked_rows)
        if len(seeds) >= limit:
            return seeds

        recent_rows = await self.session.scalars(
            select(Track)
            .join(TrackPlay, TrackPlay.track_id == Track.id)
            .where(TrackPlay.api_key_id == self.api_key_id)
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

    async def _personalization_profile(self) -> PersonalizationProfile:
        track_weights: defaultdict[UUID, float] = defaultdict(float)
        artist_weights: defaultdict[str, float] = defaultdict(float)
        album_weights: defaultdict[str, float] = defaultdict(float)
        token_weights: defaultdict[str, float] = defaultdict(float)
        seed_labels: list[str] = []

        signal_rows = await self.session.execute(
            select(PersonalizationSignal, Track)
            .join(Track, Track.id == PersonalizationSignal.track_id)
            .where(PersonalizationSignal.api_key_id == self.api_key_id)
            .order_by(PersonalizationSignal.created_at.desc())
            .limit(800)
        )
        for signal, track in signal_rows:
            weight = signal.weight * _recency_multiplier(signal.created_at)
            _add_track_interest(
                track,
                weight=weight,
                track_weights=track_weights,
                artist_weights=artist_weights,
                album_weights=album_weights,
                token_weights=token_weights,
                seed_labels=seed_labels,
            )

        liked_rows = await self.session.execute(
            select(LikedTrack, Track)
            .join(Track, Track.id == LikedTrack.track_id)
            .where(LikedTrack.api_key_id == self.api_key_id)
            .order_by(LikedTrack.created_at.desc())
            .limit(200)
        )
        for liked, track in liked_rows:
            _add_track_interest(
                track,
                weight=3.5 * _recency_multiplier(liked.created_at, half_life_days=90),
                track_weights=track_weights,
                artist_weights=artist_weights,
                album_weights=album_weights,
                token_weights=token_weights,
                seed_labels=seed_labels,
            )

        play_rows = await self.session.execute(
            select(TrackPlay, Track)
            .join(Track, Track.id == TrackPlay.track_id)
            .where(TrackPlay.api_key_id == self.api_key_id)
            .order_by(TrackPlay.played_at.desc())
            .limit(300)
        )
        for play, track in play_rows:
            _add_track_interest(
                track,
                weight=1.0 * _recency_multiplier(play.played_at),
                track_weights=track_weights,
                artist_weights=artist_weights,
                album_weights=album_weights,
                token_weights=token_weights,
                seed_labels=seed_labels,
            )

        return PersonalizationProfile(
            track_weights=dict(track_weights),
            artist_weights=dict(artist_weights),
            album_weights=dict(album_weights),
            token_weights=dict(token_weights),
            seed_labels=_dedupe_text(seed_labels)[:12],
        )

    async def _local_recommendations_for_seed(
        self,
        seed: Track,
        *,
        limit: int,
    ) -> list[LocalTrackRecommendation]:
        if limit <= 0:
            return []
        tracks = list(
            await self.session.scalars(
                select(Track)
                .where(Track.id != seed.id)
                .order_by(Track.last_accessed.desc())
                .limit(settings.recommendation_scan_limit)
            )
        )
        features = await self._features_by_track_ids([seed.id, *(track.id for track in tracks)])
        profile = await self._personalization_profile()
        neighbors = await self._collaborative_neighbors(seed.id, [track.id for track in tracks])
        scored = [
            _score_track_against_seed(
                seed,
                candidate,
                seed_feature=features.get(seed.id),
                candidate_feature=features.get(candidate.id),
                profile=profile,
                collaborative_neighbor=neighbors.get(candidate.id),
            )
            for candidate in tracks
        ]
        ranked = sorted(
            [item for item in scored if item.score > 0],
            key=lambda item: item.score,
            reverse=True,
        )
        return await self._maybe_gemini_rerank(seed, ranked, limit=limit)

    async def _local_recommendations_for_library(
        self,
        seed_tracks: list[Track],
        *,
        limit: int,
    ) -> list[LocalTrackRecommendation]:
        if not seed_tracks:
            return []
        seed_ids = {track.id for track in seed_tracks}
        candidates = list(
            await self.session.scalars(
                select(Track)
                .where(Track.id.not_in(seed_ids))
                .order_by(Track.last_accessed.desc())
                .limit(settings.recommendation_scan_limit)
            )
        )
        features = await self._features_by_track_ids(
            [*(track.id for track in seed_tracks), *(track.id for track in candidates)]
        )
        profile = await self._personalization_profile()
        vectors = {
            track_id: _normalized_audio_vector(feature)
            for track_id, feature in features.items()
        }
        best: dict[UUID, LocalTrackRecommendation] = {}
        for seed in seed_tracks:
            seed_vector = vectors.get(seed.id)
            for candidate in candidates:
                scored = _score_track_against_seed(
                    seed,
                    candidate,
                    seed_feature=features.get(seed.id),
                    candidate_feature=features.get(candidate.id),
                    profile=profile,
                    seed_vector=seed_vector,
                    candidate_vector=vectors.get(candidate.id),
                )
                current = best.get(candidate.id)
                if scored.score > 0 and (current is None or scored.score > current.score):
                    best[candidate.id] = scored
        return sorted(best.values(), key=lambda item: item.score, reverse=True)[:limit]

    async def _features_by_track_ids(self, track_ids: list[UUID]) -> dict[UUID, TrackAudioFeature]:
        unique_ids = list({track_id for track_id in track_ids})
        if not unique_ids:
            return {}
        rows = await self.session.scalars(
            select(TrackAudioFeature).where(TrackAudioFeature.track_id.in_(unique_ids))
        )
        return {row.track_id: row for row in rows}

    async def _collaborative_neighbors(
        self,
        seed_id: UUID,
        candidate_ids: list[UUID],
    ) -> dict[UUID, TrackNeighbor]:
        """Batch-fetch the global cross-user co-occurrence neighbors of ``seed_id``
        that are among ``candidate_ids``. Keyed by ``neighbor_track_id``."""
        unique_ids = list({track_id for track_id in candidate_ids})
        if not unique_ids:
            return {}
        rows = await self.session.scalars(
            select(TrackNeighbor).where(
                TrackNeighbor.track_id == seed_id,
                TrackNeighbor.neighbor_track_id.in_(unique_ids),
            )
        )
        return {row.neighbor_track_id: row for row in rows}

    async def _maybe_gemini_rerank(
        self,
        seed: Track,
        ranked: list[LocalTrackRecommendation],
        *,
        limit: int,
    ) -> list[LocalTrackRecommendation]:
        if limit <= 0:
            return []
        if not settings.recommendation_use_gemini or self.gemini_client is None:
            return ranked[:limit]
        if not self.gemini_client.is_configured:
            return ranked[:limit]

        candidates = ranked[: max(limit, settings.recommendation_gemini_candidate_limit)]
        by_id = {item.track.id: item for item in candidates}
        try:
            reranked = await self.gemini_client.rerank(
                seed=seed,
                candidates=[
                    GeminiCandidate(track=item.track, score=item.score, reasons=item.reasons)
                    for item in candidates
                ],
                redis=self.redis,
            )
        except GeminiRecommendationUnavailable as exc:
            logger.info("Gemini rerank unavailable; using local Python ranking: %s", exc)
            return ranked[:limit]

        selected: list[LocalTrackRecommendation] = []
        seen: set[UUID] = set()
        for track_id in reranked.ordered_ids:
            item = by_id.get(track_id)
            if item is None or track_id in seen:
                continue
            note = reranked.notes.get(track_id)
            reasons = [*item.reasons, "gemini_rerank"]
            if note:
                reasons.append(f"gemini_note:{note}")
            selected.append(
                LocalTrackRecommendation(
                    track=item.track,
                    score=item.score,
                    reasons=_dedupe_text(reasons),
                )
            )
            seen.add(track_id)
            if len(selected) >= limit:
                break

        for item in ranked:
            if item.track.id in seen:
                continue
            selected.append(item)
            if len(selected) >= limit:
                break
        return selected

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
        # External acquisition now happens through Lidarr (see /catalog), so the
        # recommendation engine no longer searches torrent sources itself. Local,
        # collaborative, and audio-feature recommendations are unaffected.
        return []

    async def _library_fingerprint(self) -> set[frozenset[str]]:
        tracks = await self.session.scalars(
            select(Track)
            .order_by(Track.last_accessed.desc())
            .limit(settings.recommendation_scan_limit)
        )
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


def _score_track_against_seed(
    seed: Track,
    candidate: Track,
    *,
    seed_feature: TrackAudioFeature | None = None,
    candidate_feature: TrackAudioFeature | None = None,
    profile: PersonalizationProfile | None = None,
    seed_vector: list[float] | None = None,
    candidate_vector: list[float] | None = None,
    collaborative_neighbor: TrackNeighbor | None = None,
) -> LocalTrackRecommendation:
    score = 0.0
    reasons: list[str] = []

    audio_similarity = _audio_similarity(
        seed_feature,
        candidate_feature,
        seed_vector=seed_vector,
        candidate_vector=candidate_vector,
    )
    if audio_similarity is not None:
        score += audio_similarity * 70.0
        reasons.append("audio_similarity")
        if _near_number(seed_feature.tempo, candidate_feature.tempo, tolerance=8.0):
            score += 8.0
            reasons.append("similar_tempo")
        if _near_number(seed_feature.energy, candidate_feature.energy, tolerance=0.035):
            score += 6.0
            reasons.append("similar_energy")

    if _same_text(seed.artist, candidate.artist) and seed.artist:
        score += 35.0
        reasons.append("same_artist")
    if _same_text(seed.album, candidate.album) and seed.album:
        score += 20.0
        reasons.append("same_album")

    overlap = _token_overlap(
        f"{seed.artist or ''} {seed.album or ''} {seed.title}",
        f"{candidate.artist or ''} {candidate.album or ''} {candidate.title}",
    )
    if overlap:
        score += min(18.0, overlap * 5.0)
        reasons.append("metadata_overlap")

    if seed.duration_seconds and candidate.duration_seconds:
        diff = abs(seed.duration_seconds - candidate.duration_seconds)
        if diff <= 30:
            score += 7.0
            reasons.append("similar_duration")
        elif diff <= 90:
            score += 3.0
            reasons.append("near_duration")

    if profile is not None:
        direct_weight = profile.track_weights.get(candidate.id, 0.0)
        if direct_weight:
            score += min(18.0, max(-18.0, direct_weight * 2.0))
            reasons.append("personal_signal")

        artist_key = _profile_key(candidate.artist)
        if artist_key and artist_key in profile.artist_weights:
            score += min(22.0, profile.artist_weights[artist_key] * 1.5)
            reasons.append("artist_interest")

        album_key = _profile_key(candidate.album)
        if album_key and album_key in profile.album_weights:
            score += min(10.0, profile.album_weights[album_key])
            reasons.append("album_interest")

    if collaborative_neighbor is not None:
        score += min(30.0, collaborative_neighbor.score * settings.recommendation_collaborative_weight)
        reasons.append("collaborative_signal")

    score -= _recently_played_penalty(candidate, profile)
    return LocalTrackRecommendation(track=candidate, score=round(score, 2), reasons=reasons)


def _audio_similarity(
    seed_feature: TrackAudioFeature | None,
    candidate_feature: TrackAudioFeature | None,
    *,
    seed_vector: list[float] | None = None,
    candidate_vector: list[float] | None = None,
) -> float | None:
    if seed_feature is None or candidate_feature is None:
        return None
    if seed_vector is None:
        seed_vector = _normalized_audio_vector(seed_feature)
    if candidate_vector is None:
        candidate_vector = _normalized_audio_vector(candidate_feature)
    if not seed_vector or len(seed_vector) != len(candidate_vector):
        return None
    return max(0.0, _cosine_similarity(seed_vector, candidate_vector))


def _pad_to(values: object, length: int, *, scale: float = 1.0) -> list[float]:
    """Coerce ``values`` into a fixed-length float list, zero-padding (or truncating)
    to ``length``. ``None``/empty inputs become an all-zero vector of that length, so
    v1 rows lacking the newer fields degrade gracefully instead of shrinking the vector."""
    out = [float(value) * scale for value in (values or [])][:length]
    while len(out) < length:
        out.append(0.0)
    return out


def _normalized_audio_vector(feature: TrackAudioFeature) -> list[float]:
    """Version-aware, fixed-length (52-dim) embedding usable across v1 and v2 rows.

    v1 rows (where the richer fields are ``None``/empty) zero-pad the new dimensions
    so cosine similarity between any pair (v1-v1, v1-v2, v2-v2) stays well defined and
    the earlier 17-dim scoring behavior is preserved for v1-v1 comparisons.
    """
    return [
        *_pad_to(feature.mfcc, 13, scale=1.0 / 100.0),
        *_pad_to(getattr(feature, "mfcc_delta", None), 13, scale=1.0 / 100.0),
        *_pad_to(getattr(feature, "chroma_vector", None), 12),
        *_pad_to(getattr(feature, "spectral_contrast", None), 7, scale=1.0 / 50.0),
        float(feature.tempo or 0.0) / 220.0,
        float(feature.energy or 0.0),
        # The scalar ``chroma`` mean is redundant with the 12-bin ``chroma_vector``
        # above, so it is intentionally not folded in here (keeps the vector at 52 dims).
        float(feature.spectral_centroid or 0.0) / 8_000.0,
        float(getattr(feature, "spectral_rolloff", None) or 0.0) / 8_000.0,
        float(getattr(feature, "spectral_bandwidth", None) or 0.0) / 4_000.0,
        float(getattr(feature, "zero_crossing_rate", None) or 0.0),
        # A missing HPSS ratio contributes 0.0 (not the 1.0/4.0 "neutral" default) so that
        # a fully-v1 row reduces exactly to the legacy 17-dim vector plus cosine-invariant
        # zeros — keeping v1-v1 similarity identical to the pre-existing scoring behavior.
        (
            float(feature.harmonic_percussive_ratio) / 4.0
            if getattr(feature, "harmonic_percussive_ratio", None) is not None
            else 0.0
        ),
    ]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _near_number(left: float | None, right: float | None, *, tolerance: float) -> bool:
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) <= tolerance


def _recently_played_penalty(
    candidate: Track,
    profile: PersonalizationProfile | None,
) -> float:
    if profile is None:
        return 0.0
    direct_weight = profile.track_weights.get(candidate.id, 0.0)
    if direct_weight < 0:
        return min(10.0, abs(direct_weight))
    return 0.0


def _score_personalized_tracks(
    tracks: list[Track],
    *,
    profile: PersonalizationProfile,
    day: str,
    salt: str,
) -> list[LocalTrackRecommendation]:
    if not profile.track_weights and not profile.artist_weights and not profile.album_weights:
        return [
            LocalTrackRecommendation(
                track=track,
                score=round(_daily_jitter(track.id, day=day, salt=salt) * 20.0, 2),
                reasons=["daily_shuffle"],
            )
            for track in tracks
        ]

    scored: list[LocalTrackRecommendation] = []
    for track in tracks:
        score = 0.0
        reasons: list[str] = []
        artist_key = _profile_key(track.artist)
        album_key = _profile_key(track.album)

        direct_weight = profile.track_weights.get(track.id, 0.0)
        if direct_weight:
            score += min(18.0, max(-8.0, direct_weight * 2.0))
            reasons.append("listening_history")
        if artist_key and artist_key in profile.artist_weights:
            score += min(55.0, profile.artist_weights[artist_key] * 4.0)
            reasons.append("artist_interest")
        if album_key and album_key in profile.album_weights:
            score += min(22.0, profile.album_weights[album_key] * 2.2)
            reasons.append("album_interest")

        token_hits = 0
        for token in _tokens(f"{track.title} {track.artist or ''} {track.album or ''}"):
            weight = profile.token_weights.get(token, 0.0)
            if weight > 0:
                token_hits += 1
                score += min(4.0, weight)
        if token_hits:
            reasons.append("metadata_interest")

        score += _daily_jitter(track.id, day=day, salt=salt) * 16.0
        if score > 0:
            scored.append(
                LocalTrackRecommendation(
                    track=track,
                    score=round(score, 2),
                    reasons=reasons or ["daily_shuffle"],
                )
            )

    return sorted(scored, key=lambda item: item.score, reverse=True)


def _diversify_recommendations(
    scored: list[LocalTrackRecommendation],
    *,
    limit: int,
    max_per_artist: int = 4,
) -> list[LocalTrackRecommendation]:
    if limit <= 0:
        return []
    selected: list[LocalTrackRecommendation] = []
    artist_counts: defaultdict[str, int] = defaultdict(int)
    for item in scored:
        artist_key = _profile_key(item.track.artist) or "unknown"
        if artist_counts[artist_key] >= max_per_artist:
            continue
        selected.append(item)
        artist_counts[artist_key] += 1
        if len(selected) >= limit:
            return selected

    seen = {item.track.id for item in selected}
    for item in scored:
        if item.track.id in seen:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


# Personalization reasons that mark a track as "known" (exploit) rather than a fresh
# discovery pick — a track carrying any of these has history and is not explore-eligible.
_PERSONALIZATION_REASONS = frozenset(
    {"artist_interest", "album_interest", "personal_signal", "collaborative_signal"}
)


def _sequence_autoplay_batch(
    ranked: list[LocalTrackRecommendation],
    *,
    limit: int,
    features_by_track_id: dict[UUID, TrackAudioFeature],
    profile: PersonalizationProfile,
    max_per_artist: int = 3,
) -> list[LocalTrackRecommendation]:
    """Session-aware sequencing for the autoplay radio.

    Diversify into a padded pool (so there's slack for discovery picks and reordering),
    reserve a fraction of the batch for cold "discovery" tracks (explore) alongside the
    top personalized/content picks (exploit), then reorder into a rise-then-fall energy
    arc. Used only by ``autoplay_queue`` — ``_diversify_recommendations`` is left untouched
    for ``personalized_home``.
    """
    if limit <= 0:
        return []

    pool = _diversify_recommendations(
        ranked,
        limit=min(len(ranked), limit * 2),
        max_per_artist=max_per_artist,
    )

    # ── Explore/exploit discovery slots ──────────────────────────────────────
    discovery_slots = max(0, round(limit * settings.recommendation_discovery_slot_ratio))
    chosen_discovery: list[LocalTrackRecommendation] = []
    discovery_ids: set[UUID] = set()
    if discovery_slots > 0:
        for item in pool:  # pool is already in score order
            if len(chosen_discovery) >= discovery_slots:
                break
            has_history = profile.track_weights.get(item.track.id, 0.0) != 0.0
            has_personalization_reason = any(
                reason in _PERSONALIZATION_REASONS for reason in item.reasons
            )
            if has_history or has_personalization_reason or item.score <= 0:
                continue
            # ``reasons`` lists aren't shared across items, but ``replace`` (frozen dataclass)
            # is the clean, side-effect-free way to tag the discovery pick.
            tagged = replace(item, reasons=[*item.reasons, "discovery"])
            chosen_discovery.append(tagged)
            discovery_ids.add(item.track.id)

    # ── Final selection: reserved discovery picks + top exploit picks ─────────
    # Merge approach: keep the discovery picks (already in score order), then fill the
    # remaining slots from the non-discovery pool in score order. Concatenating in that
    # order and re-sorting by score would drop the discovery items back down; instead we
    # deliberately keep discovery items even if a higher-scored exploit item exists, since
    # the slots are *reserved*. The result is then sorted by score so the batch as a whole
    # is in descending-score order before arc reordering runs.
    final_count = min(limit, len(pool))
    selected: list[LocalTrackRecommendation] = list(chosen_discovery)
    for item in pool:
        if len(selected) >= final_count:
            break
        if item.track.id in discovery_ids:
            continue
        selected.append(item)
    selected.sort(key=lambda item: item.score, reverse=True)

    return _arc_order(selected, features_by_track_id=features_by_track_id)


def _arc_order(
    selected: list[LocalTrackRecommendation],
    *,
    features_by_track_id: dict[UUID, TrackAudioFeature],
) -> list[LocalTrackRecommendation]:
    """Reorder (never filter) ``selected`` into a rise-then-fall energy arc.

    Position 0 (the top-ranked, seed-adjacent track) is fixed so the transition from the
    just-played seed track stays smooth; the arc only shapes positions 1..N-1. Tracks with
    no usable energy data keep their original relative position in the tail.
    """
    if len(selected) <= 2:
        return selected

    head = selected[0]
    tail = selected[1:]

    # Partition the tail into "has energy data" vs "no data" (preserving order).
    has_data: list[LocalTrackRecommendation] = []
    energies: list[float] = []
    for item in tail:
        feature = features_by_track_id.get(item.track.id)
        if feature is not None and feature.energy is not None:
            has_data.append(item)
            energies.append(float(feature.energy))

    m = len(has_data)
    if m == 0:
        return selected

    low = min(energies)
    high = max(energies)
    if high == low:
        # All energies equal — no meaningful arc; leave the tail in original order.
        return selected

    energy_position = [(value - low) / (high - low) for value in energies]

    # Target rise-then-fall shape: sin peaks in the middle, avoiding the degenerate
    # sin(0)=0 endpoints by offsetting the sampled positions.
    targets = [math.sin(math.pi * (i + 1) / (m + 1)) for i in range(m)]

    # Greedy nearest-fit: for each arc position, take the remaining has-data track whose
    # normalized energy is closest to the target. O(M^2), fine at M <= 50.
    remaining = list(range(m))
    arc_ordered: list[LocalTrackRecommendation] = []
    for target in targets:
        best_idx = min(remaining, key=lambda idx: abs(energy_position[idx] - target))
        arc_ordered.append(has_data[best_idx])
        remaining.remove(best_idx)

    # Re-interleave no-data tracks at their original tail slots: walk the original tail,
    # substituting the next arc-ordered has-data track wherever a has-data track sat, and
    # keeping no-data tracks in place (preserves no-data tracks' relative order).
    has_data_ids = {item.track.id for item in has_data}
    arc_iter = iter(arc_ordered)
    reordered_tail: list[LocalTrackRecommendation] = []
    for item in tail:
        if item.track.id in has_data_ids:
            reordered_tail.append(next(arc_iter))
        else:
            reordered_tail.append(item)

    return [head, *reordered_tail]


def _build_daily_mixes(
    tracks: list[Track],
    *,
    profile: PersonalizationProfile,
    day: str,
    mix_count: int,
    mix_size: int,
) -> list[DailyMix]:
    if mix_count <= 0 or mix_size <= 0:
        return []

    seeds = _daily_mix_seeds(profile, tracks, limit=max(mix_count, 1))
    mixes: list[DailyMix] = []
    used_mix_track_ids: set[UUID] = set()
    for index, (kind, key, label) in enumerate(seeds[:mix_count], start=1):
        candidates = _score_mix_candidates(
            tracks,
            profile=profile,
            kind=kind,
            key=key,
            day=day,
            salt=f"mix-{index}",
        )
        mix_tracks: list[LocalTrackRecommendation] = []
        for item in candidates:
            if item.track.id in used_mix_track_ids and len(tracks) > mix_size:
                continue
            mix_tracks.append(item)
            used_mix_track_ids.add(item.track.id)
            if len(mix_tracks) >= mix_size:
                break
        if not mix_tracks:
            continue

        featured = _mix_featured_artists(mix_tracks)
        description = f"Based on {label}"
        if featured:
            description = f"{featured} and similar picks"
        mixes.append(
            DailyMix(
                id=f"daily-mix-{day}-{index}",
                title=f"Daily Mix {index}",
                description=description,
                seed_label=label,
                tracks=mix_tracks,
            )
        )

    return mixes


def _daily_mix_seeds(
    profile: PersonalizationProfile,
    tracks: list[Track],
    *,
    limit: int,
) -> list[tuple[str, str, str]]:
    seeds: list[tuple[str, str, str]] = []
    for key, _ in sorted(profile.artist_weights.items(), key=lambda item: item[1], reverse=True):
        label = _display_label_for_key(key, [track.artist for track in tracks])
        if label:
            seeds.append(("artist", key, label))
    for key, _ in sorted(profile.album_weights.items(), key=lambda item: item[1], reverse=True):
        label = _display_label_for_key(key, [track.album for track in tracks])
        if label:
            seeds.append(("album", key, label))
    for token, _ in sorted(profile.token_weights.items(), key=lambda item: item[1], reverse=True):
        seeds.append(("token", token, token.title()))

    if not seeds:
        by_artist: defaultdict[str, list[Track]] = defaultdict(list)
        for track in tracks:
            by_artist[_profile_key(track.artist) or "unknown"].append(track)
        for key, group in sorted(by_artist.items(), key=lambda item: len(item[1]), reverse=True):
            label = group[0].artist or "your library"
            seeds.append(("artist", key, label))

    deduped: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for seed in seeds:
        seed_key = (seed[0], seed[1])
        if seed_key in seen:
            continue
        deduped.append(seed)
        seen.add(seed_key)
        if len(deduped) >= limit:
            break
    return deduped


def _score_mix_candidates(
    tracks: list[Track],
    *,
    profile: PersonalizationProfile,
    kind: str,
    key: str,
    day: str,
    salt: str,
) -> list[LocalTrackRecommendation]:
    base = _score_personalized_tracks(tracks, profile=profile, day=day, salt=salt)
    boosted: list[LocalTrackRecommendation] = []
    for item in base:
        track = item.track
        boost = 0.0
        reasons = list(item.reasons)
        if kind == "artist" and _profile_key(track.artist) == key:
            boost += 42.0
            reasons.append("daily_mix_artist")
        elif kind == "album" and _profile_key(track.album) == key:
            boost += 34.0
            reasons.append("daily_mix_album")
        elif kind == "token" and key in _tokens(f"{track.title} {track.artist or ''} {track.album or ''}"):
            boost += 28.0
            reasons.append("daily_mix_theme")
        boosted.append(
            LocalTrackRecommendation(
                track=track,
                score=round(item.score + boost, 2),
                reasons=_dedupe_text(reasons),
            )
        )
    return sorted(boosted, key=lambda item: item.score, reverse=True)


def _add_track_interest(
    track: Track,
    *,
    weight: float,
    track_weights: defaultdict[UUID, float],
    artist_weights: defaultdict[str, float],
    album_weights: defaultdict[str, float],
    token_weights: defaultdict[str, float],
    seed_labels: list[str],
) -> None:
    if weight == 0:
        return
    track_weights[track.id] += weight
    artist_key = _profile_key(track.artist)
    album_key = _profile_key(track.album)
    if artist_key:
        artist_weights[artist_key] += weight
        if weight > 0 and track.artist:
            seed_labels.append(track.artist)
    if album_key:
        album_weights[album_key] += weight * 0.65
    for token in _tokens(f"{track.title} {track.artist or ''} {track.album or ''}"):
        token_weights[token] += weight * 0.3


def _recency_multiplier(value: datetime | None, *, half_life_days: int = 45) -> float:
    if value is None:
        return 1.0
    current = datetime.now(UTC)
    comparable = value if value.tzinfo else value.replace(tzinfo=UTC)
    age_days = max((current - comparable).total_seconds() / 86_400, 0.0)
    return max(0.15, 0.5 ** (age_days / half_life_days))


def _daily_jitter(track_id: UUID, *, day: str, salt: str) -> float:
    return random.Random(f"{day}:{salt}:{track_id}").random()


def _profile_key(value: str | None) -> str | None:
    cleaned = _clean_text(value).lower()
    return cleaned or None


def _display_label_for_key(key: str, values: list[str | None]) -> str | None:
    for value in values:
        if _profile_key(value) == key and value:
            return value
    return None


def _mix_featured_artists(items: list[LocalTrackRecommendation]) -> str:
    artists = _dedupe_text([item.track.artist or "" for item in items])[:3]
    return ", ".join(artists)


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
