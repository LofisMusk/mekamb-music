from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from redis.asyncio import Redis

from app.api.deps import (
    music_indexer_provider,
    personal_1337x_provider,
    piratebay_provider,
    require_token,
)
from app.api.schemas import (
    Source1337xSearchResponse,
    SourcePirateBaySearchResponse,
    SourceSearchResponse,
)
from app.imports.queue import RedisImportQueue
from app.core.config import settings
from app.sources.indexers import MusicIndexerProvider, MusicIndexerSourceError
from app.sources.personal_1337x import (
    Personal1337xProvider,
    SourceBlockedError,
)
from app.sources.piratebay import PirateBayProvider, PirateBaySourceError
from app.sources.search import UnifiedTorrentSearch

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


@router.get("/search", response_model=SourceSearchResponse)
async def search_sources(
    q: str = Query(min_length=1, max_length=120),
    personal_1337x: Personal1337xProvider = Depends(personal_1337x_provider),
    piratebay: PirateBayProvider = Depends(piratebay_provider),
) -> SourceSearchResponse:
    redis = await _get_redis()
    search = UnifiedTorrentSearch(
        piratebay=piratebay,
        personal_1337x=personal_1337x,
    )
    results = await search.search(q, redis=redis)
    return SourceSearchResponse(items=[item.to_dict() for item in results])


@router.get("/indexers/search", response_model=SourceSearchResponse)
async def search_indexers(
    q: str = Query(min_length=1, max_length=120),
    provider: MusicIndexerProvider = Depends(music_indexer_provider),
    prowlarr_api_key: str | None = Header(default=None, alias="X-Prowlarr-Api-Key"),
) -> SourceSearchResponse:
    try:
        results = await provider.with_api_key(prowlarr_api_key).search(q)
    except MusicIndexerSourceError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return SourceSearchResponse(
        items=[
            {
                "source": item.source,
                "name": item.name,
                "torrent_id": item.torrent_id,
                "info_hash": item.info_hash,
                "magnet_link": item.magnet_link,
                "source_url": item.url,
                "seeders": item.seeders,
                "leechers": item.leechers,
                "size": None,
                "size_bytes": item.size_bytes,
                "uploader": item.uploader,
            }
            for item in results
        ],
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
