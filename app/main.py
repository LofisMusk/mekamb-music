import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status

from app.api.routes import (
    admin,
    auth,
    catalog,
    imports,
    libraries,
    library,
    playback,
    playlists,
    recommendations,
    sync,
    torznab,
    tracks,
)
from app.api.schemas import HealthResponse, ReadinessResponse
from app.catalog.lidarr_client import check_lidarr
from app.core.config import settings
from app.core.readiness import collect_readiness
from app.core.runtime import prepare_runtime
from app.db.session import check_database, init_db
from app.imports.queue import check_redis
from app.workers.audio_feature_worker import run_feature_extraction_loop
from app.workers.cache_cleanup import run_cleanup_loop
from app.workers.collaborative_filtering_worker import run_collaborative_recompute_loop
from app.workers.ia_backfill_worker import run_ia_backfill_loop
from app.workers.ia_direct_fetch_worker import run_ia_blackhole_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    prepare_runtime(settings)
    await init_db()

    # Cache TTL cleanup jako background asyncio task
    cleanup_task = asyncio.create_task(run_cleanup_loop())
    # Automatyczna ekstrakcja cech audio dla nowych/przestarzalych trackow
    feature_task = asyncio.create_task(run_feature_extraction_loop())
    # Cross-userowy recompute sasiadow trackow (collaborative filtering)
    collab_task = asyncio.create_task(run_collaborative_recompute_loop())
    # Internet Archive direct-HTTP fetch (Torrent Blackhole fallback)
    ia_blackhole_task = asyncio.create_task(run_ia_blackhole_loop())
    # Internet Archive direct-push backfill (bypasses Prowlarr/torrents entirely)
    ia_backfill_task = asyncio.create_task(run_ia_backfill_loop())

    yield

    cleanup_task.cancel()
    feature_task.cancel()
    collab_task.cancel()
    ia_blackhole_task.cancel()
    ia_backfill_task.cancel()
    for task in (cleanup_task, feature_task, collab_task, ia_blackhole_task, ia_backfill_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
app.include_router(sync.router, prefix="/sync", tags=["sync"])
app.include_router(imports.router, prefix="/imports", tags=["imports"])
app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])
app.include_router(tracks.router, prefix="/tracks", tags=["tracks"])
app.include_router(playback.router, prefix="/playback", tags=["playback"])
app.include_router(playlists.router, prefix="/playlists", tags=["playlists"])
app.include_router(libraries.router, prefix="/libraries", tags=["libraries"])
app.include_router(library.router, prefix="/library", tags=["library"])
app.include_router(torznab.router, prefix="/torznab", tags=["torznab"])


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/health/ready", response_model=ReadinessResponse)
async def readiness(response: Response) -> ReadinessResponse:
    readiness_payload = await collect_readiness(
        settings,
        database_check=check_database,
        redis_check=lambda: check_redis(settings),
        lidarr_check=lambda: check_lidarr(settings),
    )
    if readiness_payload["status"] != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(**readiness_payload)
