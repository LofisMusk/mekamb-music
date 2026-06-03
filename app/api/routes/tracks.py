from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_token
from app.api.schemas import (
    AlbumListResponse,
    ArtistListResponse,
    CacheStatsResponse,
    LikedTrackListResponse,
    LikedTrackResponse,
    PlaybackEventListResponse,
    PlaybackEventResponse,
    TrackListResponse,
    TrackResponse,
    TrackStatsResponse,
    TrackUpdateRequest,
)
from app.core.config import settings
from app.db.models import LikedTrack, PlaylistTrack, Track, TrackPlay, utcnow
from app.db.session import AsyncSessionLocal
from app.library.audio import extract_embedded_artwork, media_type_for_audio_file
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
from app.library.prefetch import prefetch_next_queue_tracks
from app.storage.library import build_library_storage
from app.workers.cache_cleanup import get_cache_stats, run_cleanup_once
from app.api.routes.playback import clear_deleted_track_from_playback
from app.sync.actions import (
    DELETE_TRACK,
    LIKE_TRACK,
    UNLIKE_TRACK,
    record_user_action,
    track_action_payload,
)

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("", response_model=TrackListResponse)
async def list_tracks(
    q: str | None = Query(default=None, min_length=1, max_length=120),
    artist: str | None = Query(default=None, min_length=1, max_length=512),
    album: str | None = Query(default=None, min_length=1, max_length=512),
    source_import_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
) -> TrackListResponse:
    normalized_query = q.strip() if q else None
    normalized_artist = artist.strip() if artist else None
    normalized_album = album.strip() if album else None
    rows = await session.scalars(
        build_track_list_query(
            q=normalized_query,
            artist=normalized_artist,
            album=normalized_album,
            source_import_id=source_import_id,
            limit=limit,
            offset=offset,
        )
    )
    return TrackListResponse(
        items=[track.to_dict() for track in rows],
        query=normalized_query,
        artist=normalized_artist,
        album=normalized_album,
        source_import_id=source_import_id,
        limit=limit,
        offset=offset,
    )


@router.get("/liked", response_model=LikedTrackListResponse)
async def list_liked_tracks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
) -> LikedTrackListResponse:
    result = await session.execute(
        select_liked_tracks(limit=limit, offset=offset)
    )
    return LikedTrackListResponse(
        items=[_liked_track_to_dict(liked_track, track) for liked_track, track in result],
        limit=limit,
        offset=offset,
    )


@router.get("/recent", response_model=PlaybackEventListResponse)
async def list_recently_played_tracks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
) -> PlaybackEventListResponse:
    result = await session.execute(
        select_recent_playback_events(limit=limit, offset=offset)
    )
    return PlaybackEventListResponse(
        items=[_playback_event_to_dict(playback_event, track) for playback_event, track in result],
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
    result = await session.execute(
        build_album_list_query(q=normalized_query, limit=limit, offset=offset)
    )
    return AlbumListResponse(
        items=[_metadata_row_to_dict(row_mapping(row)) for row in result],
        query=normalized_query,
        limit=limit,
        offset=offset,
    )


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def cache_stats() -> CacheStatsResponse:
    """Statystyki cache — total tracki, rozmiar, ile wygasłych."""
    stats = await get_cache_stats()
    return CacheStatsResponse(**stats)


@router.post("/cache/cleanup", response_model=CacheStatsResponse)
async def trigger_cleanup() -> dict:
    """Ręczny TTL cleanup — przydatne do testów i debugowania."""
    return await run_cleanup_once()


@router.get("/{track_id}", response_model=TrackResponse)
async def get_track(track_id: UUID, session: AsyncSession = Depends(db_session)) -> TrackResponse:
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")
    return TrackResponse(**track.to_dict())


@router.get("/{track_id}/stats", response_model=TrackStatsResponse)
async def get_track_stats(
    track_id: UUID,
    session: AsyncSession = Depends(db_session),
) -> TrackStatsResponse:
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    liked_track = await session.scalar(select_liked_track_for_track(track_id))
    play_count, last_played_at = (
        await session.execute(select_track_play_stats(track_id))
    ).one()
    return TrackStatsResponse(
        track=TrackResponse(**track.to_dict()),
        is_liked=liked_track is not None,
        liked_at=liked_track.created_at if liked_track else None,
        play_count=int(play_count or 0),
        last_played_at=last_played_at,
    )


@router.put("/{track_id}/like", response_model=LikedTrackResponse)
async def like_track(
    track_id: UUID,
    session: AsyncSession = Depends(db_session),
) -> LikedTrackResponse:
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    liked_track = await session.scalar(select_liked_track_for_track(track_id))
    if liked_track is None:
        liked_track = LikedTrack(track_id=track_id)
        session.add(liked_track)
        await session.commit()
        await session.refresh(liked_track)
        await record_user_action(
            session,
            action_type=LIKE_TRACK,
            entity_type="track",
            entity_id=str(track_id),
            payload=track_action_payload(track),
        )

    return LikedTrackResponse(**_liked_track_to_dict(liked_track, track))


@router.post(
    "/{track_id}/plays",
    status_code=status.HTTP_201_CREATED,
    response_model=PlaybackEventResponse,
)
async def record_track_play(
    track_id: UUID,
    session: AsyncSession = Depends(db_session),
) -> PlaybackEventResponse:
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    playback_event = TrackPlay(track_id=track_id)
    session.add(playback_event)
    await session.commit()
    await session.refresh(playback_event)
    return PlaybackEventResponse(**_playback_event_to_dict(playback_event, track))


@router.delete("/{track_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def unlike_track(
    track_id: UUID,
    session: AsyncSession = Depends(db_session),
) -> None:
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    liked_track = await session.scalar(select_liked_track_for_track(track_id))
    if liked_track is not None:
        await session.delete(liked_track)
        await session.commit()
        await record_user_action(
            session,
            action_type=UNLIKE_TRACK,
            entity_type="track",
            entity_id=str(track_id),
            payload=track_action_payload(track),
        )


@router.patch("/{track_id}", response_model=TrackResponse)
async def update_track(
    track_id: UUID,
    payload: TrackUpdateRequest,
    session: AsyncSession = Depends(db_session),
) -> TrackResponse:
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail="Provide at least one metadata field.")

    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    if "title" in payload.model_fields_set:
        if payload.title is None:
            raise HTTPException(status_code=422, detail="Title cannot be null.")
        track.title = payload.title
    if "artist" in payload.model_fields_set:
        track.artist = payload.artist
    if "album" in payload.model_fields_set:
        track.album = payload.album

    await session.commit()
    await session.refresh(track)
    return TrackResponse(**track.to_dict())


@router.delete("/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_track(
    track_id: UUID,
    delete_file: bool = Query(default=True),
    session: AsyncSession = Depends(db_session),
) -> None:
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    if delete_file:
        try:
            storage = build_library_storage(settings)
            storage.delete_file(track.storage_key)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not delete audio file from storage: {exc}",
            ) from exc

    delete_payload = track_action_payload(track)
    await session.execute(delete(PlaylistTrack).where(PlaylistTrack.track_id == track_id))
    await session.execute(delete(LikedTrack).where(LikedTrack.track_id == track_id))
    await session.execute(delete(TrackPlay).where(TrackPlay.track_id == track_id))
    await clear_deleted_track_from_playback(session, track_id)
    await session.delete(track)
    await session.commit()
    await record_user_action(
        session,
        action_type=DELETE_TRACK,
        entity_type="track",
        entity_id=str(track_id),
        payload=delete_payload,
    )


@router.get("/{track_id}/artwork")
async def get_track_artwork(
    track_id: UUID,
    session: AsyncSession = Depends(db_session),
) -> Response:
    track = await session.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found.")

    # Najpierw spróbuj cover_key z library storage (szybciej)
    if track.cover_key:
        try:
            storage = build_library_storage(settings)
            cover_path = resolve_library_file(storage.local_cache.root, track.cover_key)
            if cover_path.is_file():
                import mimetypes
                mime = mimetypes.guess_type(cover_path.name)[0] or "image/jpeg"
                return Response(
                    content=cover_path.read_bytes(),
                    media_type=mime,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        except (InvalidLibraryPath, OSError):
            pass

    # Fallback: wyciągnij z embedded tagu
    try:
        path = resolve_library_file(settings.library_root, track.storage_key)
    except InvalidLibraryPath as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid library path.") from exc

    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found.")

    try:
        artwork = extract_embedded_artwork(path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if artwork is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artwork not found.")

    return Response(
        content=artwork.data,
        media_type=artwork.media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/{track_id}/stream")
async def stream_track(
    track_id: UUID,
    background_tasks: BackgroundTasks,
    range_header: str | None = Header(default=None, alias="Range"),
    session: AsyncSession = Depends(db_session),
):
    track, path, media_type, size = await _resolve_stream_target(track_id, session)

    # Touch last_accessed w tle — nie blokuje odpowiedzi
    background_tasks.add_task(_touch_last_accessed, track_id)
    background_tasks.add_task(prefetch_next_queue_tracks)

    if range_header is None:
        return FileResponse(
            path,
            media_type=media_type,
            headers=_stream_headers(track=track, content_length=size),
        )

    try:
        range_spec = parse_range_header(range_header, size)
    except RangeNotSatisfiable as exc:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail=str(exc),
            headers={"Content-Range": f"bytes */{size}"},
        ) from exc

    headers = _stream_headers(track=track, content_length=range_spec.length)
    headers["Content-Range"] = range_spec.content_range
    return StreamingResponse(
        iter_file_range(path, range_spec.start, range_spec.end),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers=headers,
    )


@router.head("/{track_id}/stream")
async def inspect_track_stream(
    track_id: UUID,
    session: AsyncSession = Depends(db_session),
) -> Response:
    track, _, media_type, size = await _resolve_stream_target(track_id, session)
    return Response(
        status_code=status.HTTP_200_OK,
        media_type=media_type,
        headers=_stream_headers(track=track, content_length=size),
    )


async def _touch_last_accessed(track_id: UUID) -> None:
    """Aktualizuje last_accessed — background task, nie blokuje stream."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Track).where(Track.id == track_id).values(last_accessed=utcnow())
            )
            await session.commit()
    except Exception:
        pass


def _metadata_row_to_dict(row: dict[str, object]) -> dict[str, object]:
    latest = row.get("latest_track_at")
    return {
        **row,
        "latest_track_at": latest.isoformat() if hasattr(latest, "isoformat") else latest,
    }


def select_liked_tracks(*, limit: int, offset: int):
    return (
        select(LikedTrack, Track)
        .join(Track, Track.id == LikedTrack.track_id)
        .order_by(LikedTrack.created_at.desc())
        .limit(limit)
        .offset(offset)
    )


def select_liked_track_for_track(track_id: UUID):
    return select(LikedTrack).where(LikedTrack.track_id == track_id)


def select_track_play_stats(track_id: UUID):
    return select(
        func.count(TrackPlay.id),
        func.max(TrackPlay.played_at),
    ).where(TrackPlay.track_id == track_id)


def select_recent_playback_events(*, limit: int, offset: int):
    return (
        select(TrackPlay, Track)
        .join(Track, Track.id == TrackPlay.track_id)
        .order_by(TrackPlay.played_at.desc())
        .limit(limit)
        .offset(offset)
    )


def _liked_track_to_dict(liked_track: LikedTrack, track: Track) -> dict[str, object]:
    return {"track": track.to_dict(), "liked_at": liked_track.created_at.isoformat()}


def _playback_event_to_dict(playback_event: TrackPlay, track: Track) -> dict[str, object]:
    return {"track": track.to_dict(), "played_at": playback_event.played_at.isoformat()}


async def _resolve_stream_target(
    track_id: UUID,
    session: AsyncSession,
) -> tuple[Track, Path, str, int]:
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
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not prepare audio file for streaming: {exc}",
        ) from exc

    media_type = track.media_type
    if not media_type or media_type == "application/octet-stream":
        media_type = media_type_for_audio_file(path)
    return track, path, media_type, path.stat().st_size


def _stream_headers(*, track: Track, content_length: int) -> dict[str, str]:
    return {
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Disposition": _content_disposition(track.original_filename),
    }


def _content_disposition(filename: str) -> str:
    safe_filename = filename.replace("\\", "_").replace('"', "'")
    return f"inline; filename=\"{safe_filename}\"; filename*=UTF-8''{quote(filename)}"
