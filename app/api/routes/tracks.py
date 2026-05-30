from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_token
from app.api.schemas import (
    AlbumListResponse,
    ArtistListResponse,
    TrackListResponse,
    TrackResponse,
)
from app.core.config import settings
from app.db.models import Track
from app.library.queries import (
    build_album_list_query,
    build_artist_list_query,
    build_track_list_query,
    row_mapping,
)
from app.library.streaming import (
    InvalidLibraryPath,
    RangeNotSatisfiable,
    iter_file_range,
    parse_range_header,
    resolve_library_file,
)

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("", response_model=TrackListResponse)
async def list_tracks(
    q: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
) -> TrackListResponse:
    normalized_query = q.strip() if q else None
    rows = await session.scalars(
        build_track_list_query(q=normalized_query, limit=limit, offset=offset)
    )
    return TrackListResponse(
        items=[track.to_dict() for track in rows],
        query=normalized_query,
        limit=limit,
        offset=offset,
    )


@router.get("/artists", response_model=ArtistListResponse)
async def list_artists(
    q: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
) -> ArtistListResponse:
    normalized_query = q.strip() if q else None
    result = await session.execute(
        build_artist_list_query(q=normalized_query, limit=limit, offset=offset)
    )
    return ArtistListResponse(
        items=[_metadata_row_to_dict(row_mapping(row)) for row in result],
        query=normalized_query,
        limit=limit,
        offset=offset,
    )


@router.get("/albums", response_model=AlbumListResponse)
async def list_albums(
    q: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
) -> AlbumListResponse:
    normalized_query = q.strip() if q else None
    result = await session.execute(build_album_list_query(q=normalized_query, limit=limit, offset=offset))
    return AlbumListResponse(
        items=[_metadata_row_to_dict(row_mapping(row)) for row in result],
        query=normalized_query,
        limit=limit,
        offset=offset,
    )


@router.get("/{track_id}", response_model=TrackResponse)
async def get_track(track_id: UUID, session: AsyncSession = Depends(db_session)) -> TrackResponse:
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")
    return TrackResponse(**track.to_dict())


@router.get("/{track_id}/stream")
async def stream_track(
    track_id: UUID,
    range_header: str | None = Header(default=None, alias="Range"),
    session: AsyncSession = Depends(db_session),
):
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    try:
        path = resolve_library_file(settings.library_root, track.storage_key)
    except InvalidLibraryPath as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid library path.")

    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found.")

    media_type = track.media_type or "application/octet-stream"
    size = path.stat().st_size
    if range_header is None:
        return FileResponse(path, media_type=media_type, filename=track.original_filename)

    try:
        range_spec = parse_range_header(range_header, size)
    except RangeNotSatisfiable as exc:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail=str(exc),
            headers={"Content-Range": f"bytes */{size}"},
        ) from exc

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Range": range_spec.content_range,
        "Content-Length": str(range_spec.length),
    }
    return StreamingResponse(
        iter_file_range(path, range_spec.start, range_spec.end),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers=headers,
    )


def _metadata_row_to_dict(row: dict[str, object]) -> dict[str, object]:
    latest = row.get("latest_track_at")
    return {
        **row,
        "latest_track_at": latest.isoformat() if hasattr(latest, "isoformat") else latest,
    }
