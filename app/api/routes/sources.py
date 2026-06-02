from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis

from app.api.deps import personal_1337x_provider, piratebay_provider, require_token
from app.api.schemas import Source1337xSearchResponse, SourcePirateBaySearchResponse
from app.imports.queue import RedisImportQueue
from app.core.config import settings
from app.sources.personal_1337x import (
    Personal1337xProvider,
    SourceBlockedError,
)
from app.sources.piratebay import PirateBayProvider, PirateBaySourceError

router = APIRouter(dependencies=[Depends(require_token)])


async def _get_redis() -> Redis:
    queue = RedisImportQueue.from_settings(settings)
    return queue.client


@router.get("/1337x/search", response_model=Source1337xSearchResponse)
async def search_personal_1337x(
    q: str = Query(min_length=1, max_length=120),
    page: int = Query(default=1, ge=1, le=5),
    sort_by: str = Query(default="seeders", pattern="^(seeders|time)$"),
    provider: Personal1337xProvider = Depends(personal_1337x_provider),
) -> Source1337xSearchResponse:
    redis = await _get_redis()
    try:
        results = await provider.search(q, page=page, sort_by=sort_by, redis=redis)
    except SourceBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return Source1337xSearchResponse(
        items=[item.to_dict() for item in results],
    )


@router.get("/piratebay/search", response_model=SourcePirateBaySearchResponse)
async def search_piratebay(
    q: str = Query(min_length=1, max_length=120),
    provider: PirateBayProvider = Depends(piratebay_provider),
) -> SourcePirateBaySearchResponse:
    try:
        results = await provider.search(q)
    except PirateBaySourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return SourcePirateBaySearchResponse(
        items=[item.to_dict() for item in results],
    )
