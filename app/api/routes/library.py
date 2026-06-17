from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_token
from app.api.schemas import LibrarySummaryResponse
from app.core.auth import ApiKeyIdentity
from app.db.models import ImportJob, LikedTrack, Playlist, Track, TrackPlay
from app.imports.domain import ImportStatus

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/summary", response_model=LibrarySummaryResponse)
async def get_library_summary(
    api_key: ApiKeyIdentity = Depends(require_token),
    session: AsyncSession = Depends(db_session),
) -> LibrarySummaryResponse:
    artist_name = func.coalesce(Track.artist, "Unknown Artist")
    album_title = func.coalesce(Track.album, "Unknown Album")
    album_artist = func.coalesce(Track.artist, "Unknown Artist")

    track_count, size_bytes, duration_seconds, latest_track_at = (
        await session.execute(
            select(
                func.count(Track.id),
                func.coalesce(func.sum(Track.size_bytes), 0),
                func.coalesce(func.sum(Track.duration_seconds), 0),
                func.max(Track.created_at),
            )
        )
    ).one()

    return LibrarySummaryResponse(
        track_count=int(track_count or 0),
        artist_count=await _count_grouped(
            session,
            select(artist_name).group_by(artist_name),
        ),
        album_count=await _count_grouped(
            session,
            select(album_title, album_artist).group_by(album_title, album_artist),
        ),
        playlist_count=await _count_rows(session, Playlist.id, Playlist.api_key_id == api_key.id),
        liked_track_count=await _count_rows(session, LikedTrack.id, LikedTrack.api_key_id == api_key.id),
        playback_event_count=await _count_rows(session, TrackPlay.id, TrackPlay.api_key_id == api_key.id),
        import_count=await _count_rows(session, ImportJob.id),
        active_import_count=await _count_imports_by_status(session, ImportStatus.active()),
        failed_import_count=await _count_imports_by_status(session, (ImportStatus.FAILED.value,)),
        library_size_bytes=int(size_bytes or 0),
        total_duration_seconds=int(duration_seconds or 0),
        latest_track_at=latest_track_at,
        latest_import_at=await _latest_import_at(session),
    )


async def _count_rows(session: AsyncSession, column, *conditions) -> int:
    statement = select(func.count(column))
    if conditions:
        statement = statement.where(*conditions)
    count = await session.scalar(statement)
    return int(count or 0)


async def _count_grouped(session: AsyncSession, statement) -> int:
    count = await session.scalar(select(func.count()).select_from(statement.subquery()))
    return int(count or 0)


async def _count_imports_by_status(session: AsyncSession, statuses: tuple[str, ...]) -> int:
    count = await session.scalar(
        select(func.count(ImportJob.id)).where(ImportJob.status.in_(statuses))
    )
    return int(count or 0)


async def _latest_import_at(session: AsyncSession):
    return await session.scalar(select(func.max(ImportJob.created_at)))
