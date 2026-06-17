from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    db_session,
    import_service,
    music_indexer_provider,
    personal_1337x_provider,
    piratebay_provider,
    require_token,
)
from app.api.schemas import (
    DailyMixResponse,
    PersonalizedHomeResponse,
    RecommendationImportItemResponse,
    RecommendationImportRequest,
    RecommendationImportResponse,
    RecommendationResponse,
)
from app.core.auth import ApiKeyIdentity
from app.core.config import settings
from app.imports.service import ImportService
from app.recommendations.engine import ExternalRecommendation, RecommendationEngine, RecommendationSet
from app.sources.indexers import MusicIndexerProvider
from app.sources.personal_1337x import Personal1337xProvider
from app.sources.piratebay import PirateBayProvider
from app.sync.actions import IMPORT_TORRENT, import_action_payload, record_user_action

router = APIRouter(dependencies=[Depends(require_token)])


def _recommendation_engine(
    session: AsyncSession = Depends(db_session),
    api_key: ApiKeyIdentity = Depends(require_token),
    indexer: MusicIndexerProvider = Depends(music_indexer_provider),
    piratebay: PirateBayProvider = Depends(piratebay_provider),
    personal_1337x: Personal1337xProvider = Depends(personal_1337x_provider),
) -> RecommendationEngine:
    return RecommendationEngine(
        session=session,
        indexer=indexer,
        piratebay=piratebay,
        personal_1337x=personal_1337x,
        api_key_id=api_key.id,
    )


@router.get("/tracks/{track_id}", response_model=RecommendationResponse)
async def recommend_for_track(
    track_id: UUID,
    local_limit: int = Query(default=12, ge=0, le=100),
    external_limit: int = Query(default=12, ge=0, le=50),
    sources: str | None = Query(default=None),
    engine: RecommendationEngine = Depends(_recommendation_engine),
) -> RecommendationResponse:
    try:
        recommendations = await engine.recommend_for_track(
            track_id,
            local_limit=local_limit,
            external_limit=external_limit,
            sources=_sources(sources),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _recommendation_response(recommendations)


@router.get("/library", response_model=RecommendationResponse)
async def recommend_for_library(
    local_limit: int = Query(default=24, ge=0, le=200),
    external_limit: int = Query(default=20, ge=0, le=100),
    sources: str | None = Query(default=None),
    engine: RecommendationEngine = Depends(_recommendation_engine),
) -> RecommendationResponse:
    recommendations = await engine.recommend_for_library(
        local_limit=local_limit,
        external_limit=external_limit,
        sources=_sources(sources),
    )
    return _recommendation_response(recommendations)


@router.get("/personalized", response_model=PersonalizedHomeResponse)
async def personalized_home(
    local_limit: int = Query(default=24, ge=1, le=100),
    mix_count: int = Query(default=4, ge=1, le=8),
    mix_size: int = Query(default=12, ge=1, le=50),
    engine: RecommendationEngine = Depends(_recommendation_engine),
) -> PersonalizedHomeResponse:
    home = await engine.personalized_home(
        local_limit=local_limit,
        mix_count=mix_count,
        mix_size=mix_size,
    )
    return PersonalizedHomeResponse(
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


@router.post("/tracks/{track_id}/import-missing", response_model=RecommendationImportResponse)
async def import_missing_for_track(
    track_id: UUID,
    request: RecommendationImportRequest | None = None,
    engine: RecommendationEngine = Depends(_recommendation_engine),
    api_key: ApiKeyIdentity = Depends(require_token),
    session: AsyncSession = Depends(db_session),
    service: ImportService = Depends(import_service),
    indexer: MusicIndexerProvider = Depends(music_indexer_provider),
    piratebay: PirateBayProvider = Depends(piratebay_provider),
    personal_1337x: Personal1337xProvider = Depends(personal_1337x_provider),
) -> RecommendationImportResponse:
    payload = request or RecommendationImportRequest(
        limit=settings.recommendation_auto_import_limit,
        min_seeders=settings.recommendation_min_seeders,
    )
    try:
        recommendations = await engine.recommend_for_track(
            track_id,
            local_limit=0,
            external_limit=max(payload.limit * 4, payload.limit),
            sources=payload.sources or _sources(None),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return await _import_missing(
        recommendations.external_candidates,
        request=payload,
        session=session,
        api_key_id=api_key.id,
        service=service,
        indexer=indexer,
        piratebay=piratebay,
        personal_1337x=personal_1337x,
    )


@router.post("/library/import-missing", response_model=RecommendationImportResponse)
async def import_missing_for_library(
    request: RecommendationImportRequest | None = None,
    engine: RecommendationEngine = Depends(_recommendation_engine),
    api_key: ApiKeyIdentity = Depends(require_token),
    session: AsyncSession = Depends(db_session),
    service: ImportService = Depends(import_service),
    indexer: MusicIndexerProvider = Depends(music_indexer_provider),
    piratebay: PirateBayProvider = Depends(piratebay_provider),
    personal_1337x: Personal1337xProvider = Depends(personal_1337x_provider),
) -> RecommendationImportResponse:
    payload = request or RecommendationImportRequest(
        limit=settings.recommendation_auto_import_limit,
        min_seeders=settings.recommendation_min_seeders,
    )
    recommendations = await engine.recommend_for_library(
        local_limit=0,
        external_limit=max(payload.limit * 4, payload.limit),
        sources=payload.sources or _sources(None),
    )
    return await _import_missing(
        recommendations.external_candidates,
        request=payload,
        session=session,
        api_key_id=api_key.id,
        service=service,
        indexer=indexer,
        piratebay=piratebay,
        personal_1337x=personal_1337x,
    )
async def _import_missing(
    candidates: list[ExternalRecommendation],
    *,
    request: RecommendationImportRequest,
    session: AsyncSession,
    api_key_id: str,
    service: ImportService,
    indexer: MusicIndexerProvider,
    piratebay: PirateBayProvider,
    personal_1337x: Personal1337xProvider,
) -> RecommendationImportResponse:
    imported: list[RecommendationImportItemResponse] = []
    skipped: list[RecommendationImportItemResponse] = []
    failed: list[RecommendationImportItemResponse] = []
    allowed_sources = {source.lower() for source in (request.sources or _sources(None))}

    for candidate in candidates:
        item_response = _candidate_response(candidate)
        if len(imported) >= request.limit:
            skipped.append(RecommendationImportItemResponse(candidate=item_response, error="limit_reached"))
            continue
        if candidate.already_in_library:
            skipped.append(RecommendationImportItemResponse(candidate=item_response, error="already_in_library"))
            continue
        if candidate.item.source.lower() not in allowed_sources:
            skipped.append(RecommendationImportItemResponse(candidate=item_response, error="source_not_allowed"))
            continue
        if _seeders(candidate.item.seeders) < request.min_seeders:
            skipped.append(RecommendationImportItemResponse(candidate=item_response, error="not_enough_seeders"))
            continue

        try:
            record = await _create_import(
                candidate,
                service=service,
                indexer=indexer,
                piratebay=piratebay,
                personal_1337x=personal_1337x,
            )
            await record_user_action(
                session,
                action_type=IMPORT_TORRENT,
                entity_type="import",
                entity_id=str(record.id),
                payload=import_action_payload(record),
                api_key_id=api_key_id,
            )
            imported.append(
                RecommendationImportItemResponse(
                    candidate=item_response,
                    import_record=record.to_dict(),
                )
            )
        except Exception as exc:
            failed.append(RecommendationImportItemResponse(candidate=item_response, error=str(exc)))

    return RecommendationImportResponse(imported=imported, skipped=skipped, failed=failed)


async def _create_import(
    candidate: ExternalRecommendation,
    *,
    service: ImportService,
    indexer: MusicIndexerProvider,
    piratebay: PirateBayProvider,
    personal_1337x: Personal1337xProvider,
):
    item = candidate.item
    if item.source == "indexer":
        import_candidate = indexer.candidate_from_payload(item.to_dict() | {"name": item.name})
        return await service.create_indexer_import(import_candidate)
    if item.source == "piratebay":
        import_candidate = await piratebay.resolve_for_import(item.torrent_id)
        return await service.create_piratebay_import(import_candidate)
    if item.source == "1337x":
        import_candidate = await personal_1337x.resolve_for_import(item.torrent_id)
        return await service.create_1337x_import(import_candidate)
    raise ValueError(f"Unsupported recommendation source {item.source!r}.")


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


def _candidate_response(candidate: ExternalRecommendation) -> dict[str, object]:
    return {
        "item": candidate.item.to_dict(),
        "score": candidate.score,
        "query": candidate.query,
        "reasons": candidate.reasons,
        "already_in_library": candidate.already_in_library,
    }


def _sources(raw: str | None) -> list[str]:
    value = raw if raw is not None else settings.recommendation_sources
    sources = [item.strip().lower() for item in value.split(",") if item.strip()]
    return sources or ["indexer"]


def _seeders(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return 0
