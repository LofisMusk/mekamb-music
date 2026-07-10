from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, import_service, lidarr_client, require_token, require_user
from app.api.schemas import (
    CatalogAddRequest,
    CatalogRequestListResponse,
    CatalogSearchItemResponse,
    CatalogSearchResponse,
)
from app.catalog.lidarr_client import LidarrClient, LidarrError, LidarrNotConfigured
from app.core.auth import ApiKeyIdentity
from app.core.config import settings
from app.db.models import CatalogRequest
from app.imports.service import ImportService, InvalidImportCandidate, SandboxViolation

logger = logging.getLogger("uvicorn.error")

# Note: /catalog/webhook must stay unauthenticated (Lidarr calls it with a shared
# secret), so auth is applied per-route rather than router-wide.
router = APIRouter()


@router.get("/search", response_model=CatalogSearchResponse)
async def search_catalog(
    q: str = Query(min_length=1, max_length=256),
    kind: str = Query(default="artist", pattern="^(artist|album)$"),
    _user=Depends(require_user),
    client: LidarrClient = Depends(lidarr_client),
) -> CatalogSearchResponse:
    try:
        raw = client.lookup(kind, q)
    except LidarrNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except LidarrError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    items = [_search_item(kind, entry) for entry in raw]
    return CatalogSearchResponse(
        items=[item for item in items if item is not None],
        kind=kind,
        query=q,
    )


@router.post("/add", status_code=status.HTTP_202_ACCEPTED, response_model=CatalogRequestListResponse)
async def add_to_catalog(
    payload: CatalogAddRequest,
    api_key: ApiKeyIdentity = Depends(require_token),
    _user=Depends(require_user),
    client: LidarrClient = Depends(lidarr_client),
    session: AsyncSession = Depends(db_session),
) -> CatalogRequestListResponse:
    existing = await session.scalar(
        select(CatalogRequest).where(
            CatalogRequest.kind == payload.kind,
            CatalogRequest.foreign_id == payload.foreign_id,
        )
    )
    if existing is None:
        try:
            if payload.kind == "artist":
                client.add_artist(foreign_artist_id=payload.foreign_id, artist_name=payload.title)
            else:
                if not payload.artist_foreign_id or not payload.artist:
                    raise HTTPException(
                        status_code=422,
                        detail="Album additions require artist and artist_foreign_id.",
                    )
                client.add_album(
                    foreign_album_id=payload.foreign_id,
                    album_title=payload.title,
                    foreign_artist_id=payload.artist_foreign_id,
                    artist_name=payload.artist,
                )
        except LidarrNotConfigured as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except LidarrError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        session.add(
            CatalogRequest(
                api_key_id=api_key.id,
                kind=payload.kind,
                foreign_id=payload.foreign_id,
                title=payload.title,
                status="requested",
            )
        )
        await session.commit()

    return await _list_requests(session)


@router.get("/requests", response_model=CatalogRequestListResponse)
async def list_catalog_requests(
    _key: ApiKeyIdentity = Depends(require_token),
    _user=Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> CatalogRequestListResponse:
    return await _list_requests(session)


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def lidarr_webhook(
    request: Request,
    token: str | None = Query(default=None),
    x_webhook_token: str | None = Header(default=None),
    service: ImportService = Depends(import_service),
    session: AsyncSession = Depends(db_session),
) -> dict[str, object]:
    expected = settings.lidarr_webhook_token.strip()
    if expected and (token or x_webhook_token) != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token.")

    payload = await request.json()
    event_type = str(payload.get("eventType", "")).lower()
    if event_type in ("test", "healthissue", "applicationupdate"):
        return {"status": "ignored", "event": event_type}

    album_dir = _album_dir_from_payload(payload)
    if album_dir is None:
        return {"status": "ignored", "reason": "no track files in payload"}

    foreign_key = _foreign_key_from_payload(payload)
    name = _album_name_from_payload(payload)
    try:
        record = await service.create_lidarr_import(
            source_dir=album_dir,
            foreign_key=foreign_key,
            name=name,
            source_url="lidarr",
        )
    except (InvalidImportCandidate, SandboxViolation) as exc:
        logger.warning("Lidarr webhook ingest rejected: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await _mark_request_imported(session, foreign_key, payload)
    return {"status": "queued", "import_id": str(record.id)}


def _search_item(kind: str, entry: dict[str, Any]) -> CatalogSearchItemResponse | None:
    if not isinstance(entry, dict):
        return None
    if kind == "album":
        foreign_id = str(entry.get("foreignAlbumId") or "").strip()
        artist = entry.get("artist") or {}
        if not foreign_id:
            return None
        return CatalogSearchItemResponse(
            kind="album",
            foreign_id=foreign_id,
            title=str(entry.get("title") or "").strip() or "Unknown album",
            artist=str(artist.get("artistName") or "").strip() or None,
            artist_foreign_id=str(artist.get("foreignArtistId") or "").strip() or None,
            disambiguation=str(entry.get("disambiguation") or "").strip() or None,
            year=_year(entry.get("releaseDate")),
        )
    foreign_id = str(entry.get("foreignArtistId") or "").strip()
    if not foreign_id:
        return None
    return CatalogSearchItemResponse(
        kind="artist",
        foreign_id=foreign_id,
        title=str(entry.get("artistName") or "").strip() or "Unknown artist",
        disambiguation=str(entry.get("disambiguation") or "").strip() or None,
    )


def _album_dir_from_payload(payload: dict[str, Any]) -> str | None:
    from pathlib import Path

    track_files = payload.get("trackFiles")
    if isinstance(track_files, list):
        for track_file in track_files:
            path = track_file.get("path") if isinstance(track_file, dict) else None
            if path:
                return str(Path(path).parent)
    album = payload.get("album") or {}
    path = album.get("path") if isinstance(album, dict) else None
    if path:
        return str(path)
    return None


def _foreign_key_from_payload(payload: dict[str, Any]) -> str:
    album = payload.get("album") or {}
    if isinstance(album, dict):
        for field in ("foreignAlbumId", "id"):
            value = album.get(field)
            if value:
                return f"lidarr:{value}"
    return f"lidarr:{payload.get('id', 'unknown')}"


def _album_name_from_payload(payload: dict[str, Any]) -> str:
    album = payload.get("album") or {}
    artist = payload.get("artist") or {}
    title = album.get("title") if isinstance(album, dict) else None
    artist_name = artist.get("artistName") if isinstance(artist, dict) else None
    if title and artist_name:
        return f"{artist_name} - {title}"
    return str(title or artist_name or "Lidarr import")


def _year(release_date: object) -> int | None:
    if isinstance(release_date, str) and len(release_date) >= 4 and release_date[:4].isdigit():
        return int(release_date[:4])
    return None


async def _list_requests(session: AsyncSession) -> CatalogRequestListResponse:
    rows = await session.scalars(
        select(CatalogRequest).order_by(CatalogRequest.created_at.desc()).limit(200)
    )
    return CatalogRequestListResponse(items=[row.to_dict() for row in rows])


async def _mark_request_imported(session: AsyncSession, foreign_key: str, payload: dict[str, Any]) -> None:
    album = payload.get("album") or {}
    foreign_id = str(album.get("foreignAlbumId") or "").strip() if isinstance(album, dict) else ""
    if not foreign_id:
        return
    row = await session.scalar(
        select(CatalogRequest).where(
            CatalogRequest.kind == "album",
            CatalogRequest.foreign_id == foreign_id,
        )
    )
    if row is not None:
        row.status = "imported"
        await session.commit()
