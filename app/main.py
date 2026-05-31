import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import downloads, imports, library, playlists, sources, tracks
from app.api.schemas import HealthResponse, ReadinessResponse
from app.core.config import settings
from app.core.readiness import collect_readiness
from app.core.runtime import prepare_runtime
from app.db.session import check_database, init_db
from app.downloads.qbittorrent import check_qbittorrent
from app.imports.queue import check_redis
from app.workers.cache_cleanup import run_cleanup_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    prepare_runtime(settings)
    await init_db()

    # Cache TTL cleanup jako background asyncio task
    cleanup_task = asyncio.create_task(run_cleanup_loop())

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


WEB_ROOT = Path(__file__).parent / "web"
STATIC_ROOT = WEB_ROOT / "static"


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(sources.router, prefix="/sources", tags=["sources"])
app.include_router(imports.router, prefix="/imports", tags=["imports"])
app.include_router(downloads.router, prefix="/downloads", tags=["downloads"])
app.include_router(tracks.router, prefix="/tracks", tags=["tracks"])
app.include_router(playlists.router, prefix="/playlists", tags=["playlists"])
app.include_router(library.router, prefix="/library", tags=["library"])
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


@app.get("/", include_in_schema=False)
async def frontend() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.head("/", include_in_schema=False)
async def frontend_head() -> Response:
    return Response(status_code=status.HTTP_200_OK)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/health/ready", response_model=ReadinessResponse)
async def readiness(response: Response) -> ReadinessResponse:
    readiness_payload = await collect_readiness(
        settings,
        database_check=check_database,
        redis_check=lambda: check_redis(settings),
        torrent_client_check=lambda: check_qbittorrent(settings),
    )
    if readiness_payload["status"] != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(**readiness_payload)
