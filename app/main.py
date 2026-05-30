from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status

from app.api.routes import downloads, imports, sources, tracks
from app.api.schemas import HealthResponse, ReadinessResponse
from app.core.config import settings
from app.core.readiness import collect_readiness
from app.core.runtime import prepare_runtime
from app.db.session import check_database, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    prepare_runtime(settings)
    await init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(sources.router, prefix="/sources", tags=["sources"])
app.include_router(imports.router, prefix="/imports", tags=["imports"])
app.include_router(downloads.router, prefix="/downloads", tags=["downloads"])
app.include_router(tracks.router, prefix="/tracks", tags=["tracks"])


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/health/ready", response_model=ReadinessResponse)
async def readiness(response: Response) -> ReadinessResponse:
    readiness_payload = await collect_readiness(settings, database_check=check_database)
    if readiness_payload["status"] != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(**readiness_payload)
