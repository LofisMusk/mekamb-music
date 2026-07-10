import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    db_session,
    redis_client,
    require_token,
)
from app.api.schemas import (
    AutoplayQueueResponse,
    DailyMixResponse,
    PersonalizedHomeResponse,
    RecommendationResponse,
    TrackAudioFeatureResponse,
)
from app.core.auth import ApiKeyIdentity
from app.core.config import settings
from app.db.models import Track, TrackAudioFeature, utcnow
from app.recommendations.audio_features import (
    AudioFeatureExtractionUnavailable,
    extract_audio_features,
)
from app.recommendations.engine import ExternalRecommendation, RecommendationEngine, RecommendationSet
from app.recommendations.gemini import GeminiRecommendationClient
from app.storage.library import build_library_storage

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_token)])


def _recommendation_engine(
    session: AsyncSession = Depends(db_session),
    api_key: ApiKeyIdentity = Depends(require_token),
    redis: Redis = Depends(redis_client),
) -> RecommendationEngine:
    gemini_client = None
    if settings.recommendation_use_gemini:
        gemini_client = GeminiRecommendationClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            cache_ttl_seconds=settings.gemini_rerank_cache_ttl_seconds,
        )
    return RecommendationEngine(
        session=session,
        api_key_id=api_key.id,
        gemini_client=gemini_client,
        redis=redis,
    )


async def _cached_response(redis: Redis, key: str) -> dict[str, object] | None:
    try:
        cached = await redis.get(key)
    except Exception as exc:
        logger.warning("Redis get failed (ignored): %s", exc)
        return None
    if not cached:
        return None
    try:
        return json.loads(cached)
    except (TypeError, ValueError) as exc:
        logger.warning("Failed to decode cached recommendation response (ignored): %s", exc)
        return None


async def _store_response(redis: Redis, key: str, payload: dict[str, object]) -> None:
    try:
        await redis.setex(key, settings.recommendation_cache_ttl_seconds, json.dumps(payload))
    except Exception as exc:
        logger.warning("Redis set failed (ignored): %s", exc)


@router.get("/tracks/{track_id}", response_model=RecommendationResponse)
async def recommend_for_track(
    track_id: UUID,
    local_limit: int = Query(default=12, ge=0, le=100),
    external_limit: int = Query(default=12, ge=0, le=50),
    sources: str | None = Query(default=None),
    engine: RecommendationEngine = Depends(_recommendation_engine),
    api_key: ApiKeyIdentity = Depends(require_token),
    redis: Redis = Depends(redis_client),
) -> RecommendationResponse:
    resolved_sources = _sources(sources)
    cache_key = (
        f"rec:track:{api_key.id}:{track_id}:{local_limit}:{external_limit}:"
        f"{','.join(sorted(resolved_sources))}"
    )
    cached = await _cached_response(redis, cache_key)
    if cached is not None:
        return RecommendationResponse.model_validate(cached)

    try:
        recommendations = await engine.recommend_for_track(
            track_id,
            local_limit=local_limit,
            external_limit=external_limit,
            sources=resolved_sources,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    response = _recommendation_response(recommendations)
    await _store_response(redis, cache_key, response.model_dump(mode="json"))
    return response


@router.post("/tracks/{track_id}/audio-features", response_model=TrackAudioFeatureResponse)
async def extract_track_audio_features(
    track_id: UUID,
    session: AsyncSession = Depends(db_session),
) -> TrackAudioFeatureResponse:
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    try:
        storage = build_library_storage(settings)
        path = storage.ensure_cached(track.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid library path.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found.") from exc

    try:
        extracted = extract_audio_features(path)
    except AudioFeatureExtractionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    row = await session.scalar(
        select(TrackAudioFeature).where(TrackAudioFeature.track_id == track_id)
    )
    if row is None:
        row = TrackAudioFeature(track_id=track_id)
        session.add(row)
    row.tempo = extracted.tempo
    row.energy = extracted.energy
    row.chroma = extracted.chroma
    row.spectral_centroid = extracted.spectral_centroid
    row.mfcc = extracted.mfcc
    row.mood_tags = extracted.mood_tags
    row.chroma_vector = extracted.chroma_vector
    row.mfcc_delta = extracted.mfcc_delta
    row.spectral_contrast = extracted.spectral_contrast
    row.spectral_rolloff = extracted.spectral_rolloff
    row.spectral_bandwidth = extracted.spectral_bandwidth
    row.zero_crossing_rate = extracted.zero_crossing_rate
    row.harmonic_percussive_ratio = extracted.harmonic_percussive_ratio
    row.extractor = "librosa"
    row.features_version = settings.audio_feature_current_version
    row.extracted_at = utcnow()
    await session.commit()
    await session.refresh(row)
    return _audio_feature_response(row)


@router.get("/library", response_model=RecommendationResponse)
async def recommend_for_library(
    local_limit: int = Query(default=24, ge=0, le=200),
    external_limit: int = Query(default=20, ge=0, le=100),
    sources: str | None = Query(default=None),
    engine: RecommendationEngine = Depends(_recommendation_engine),
    api_key: ApiKeyIdentity = Depends(require_token),
    redis: Redis = Depends(redis_client),
) -> RecommendationResponse:
    resolved_sources = _sources(sources)
    cache_key = (
        f"rec:library:{api_key.id}:{local_limit}:{external_limit}:"
        f"{','.join(sorted(resolved_sources))}"
    )
    cached = await _cached_response(redis, cache_key)
    if cached is not None:
        return RecommendationResponse.model_validate(cached)

    recommendations = await engine.recommend_for_library(
        local_limit=local_limit,
        external_limit=external_limit,
        sources=resolved_sources,
    )
    response = _recommendation_response(recommendations)
    await _store_response(redis, cache_key, response.model_dump(mode="json"))
    return response


@router.get("/autoplay", response_model=AutoplayQueueResponse)
async def autoplay_queue(
    seed_track_id: UUID = Query(...),
    exclude: str | None = Query(default=None, description="Comma-separated track IDs already in the queue."),
    limit: int = Query(default=20, ge=1, le=50),
    engine: RecommendationEngine = Depends(_recommendation_engine),
) -> AutoplayQueueResponse:
    try:
        items = await engine.autoplay_queue(
            seed_track_id,
            exclude_track_ids=_parse_uuid_list(exclude),
            limit=limit,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    seed = await engine.session.get(Track, seed_track_id)
    return AutoplayQueueResponse(
        seed_track=seed.to_dict(),
        tracks=[
            {
                "track": item.track.to_dict(),
                "score": item.score,
                "reasons": item.reasons,
            }
            for item in items
        ],
    )


def _parse_uuid_list(raw: str | None) -> set[UUID]:
    if not raw:
        return set()
    ids: set[UUID] = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.add(UUID(chunk))
        except ValueError:
            continue
    return ids


@router.get("/personalized", response_model=PersonalizedHomeResponse)
async def personalized_home(
    local_limit: int = Query(default=24, ge=1, le=100),
    mix_count: int = Query(default=4, ge=1, le=8),
    mix_size: int = Query(default=12, ge=1, le=50),
    engine: RecommendationEngine = Depends(_recommendation_engine),
    api_key: ApiKeyIdentity = Depends(require_token),
    redis: Redis = Depends(redis_client),
) -> PersonalizedHomeResponse:
    cache_key = f"rec:home:{api_key.id}:{local_limit}:{mix_count}:{mix_size}"
    cached = await _cached_response(redis, cache_key)
    if cached is not None:
        return PersonalizedHomeResponse.model_validate(cached)

    home = await engine.personalized_home(
        local_limit=local_limit,
        mix_count=mix_count,
        mix_size=mix_size,
    )
    response = PersonalizedHomeResponse(
        recommended_tracks=[
            {
                "track": item.track.to_dict(),
                "score": item.score,
                "reasons": item.reasons,
            }
            for item in home.recommended_tracks
        ],
        daily_mixes=[
            DailyMixResponse(
                id=mix.id,
                title=mix.title,
                description=mix.description,
                seed_label=mix.seed_label,
                tracks=[
                    {
                        "track": item.track.to_dict(),
                        "score": item.score,
                        "reasons": item.reasons,
                    }
                    for item in mix.tracks
                ],
            )
            for mix in home.daily_mixes
        ],
    )
    await _store_response(redis, cache_key, response.model_dump(mode="json"))
    return response


def _recommendation_response(recommendations: RecommendationSet) -> RecommendationResponse:
    return RecommendationResponse(
        seed_track=recommendations.seed_track.to_dict() if recommendations.seed_track else None,
        local_tracks=[
            {
                "track": item.track.to_dict(),
                "score": item.score,
                "reasons": item.reasons,
            }
            for item in recommendations.local_tracks
        ],
        external_candidates=[_candidate_response(item) for item in recommendations.external_candidates],
    )


def _audio_feature_response(row: TrackAudioFeature) -> TrackAudioFeatureResponse:
    return TrackAudioFeatureResponse(
        track_id=row.track_id,
        tempo=row.tempo,
        energy=row.energy,
        chroma=row.chroma,
        spectral_centroid=row.spectral_centroid,
        mfcc=[float(value) for value in (row.mfcc or [])],
        mood_tags=[str(value) for value in (row.mood_tags or [])],
        extractor=row.extractor,
        features_version=row.features_version,
        extracted_at=row.extracted_at,
    )


def _candidate_response(candidate: ExternalRecommendation) -> dict[str, object]:
    return {
        "item": candidate.item.to_dict(),
        "score": candidate.score,
        "query": candidate.query,
        "reasons": candidate.reasons,
        "already_in_library": candidate.already_in_library,
    }


def _sources(raw: str | None) -> list[str]:
    # External torrent sources were replaced by Lidarr acquisition; the `sources`
    # query parameter is kept for backward compatibility but no longer selects
    # any live external search.
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]
