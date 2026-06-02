from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_token
from app.api.schemas import PlaybackStateResponse, PlaybackStateUpdateRequest
from app.db.models import PlaybackQueueItem, PlaybackState, Track, utcnow

router = APIRouter(dependencies=[Depends(require_token)])

DEFAULT_STATE_ID = "default"


@router.get("/state", response_model=PlaybackStateResponse)
async def get_playback_state(
    session: AsyncSession = Depends(db_session),
) -> PlaybackStateResponse:
    return PlaybackStateResponse(**await _load_state_payload(session))


@router.put("/state", response_model=PlaybackStateResponse)
async def update_playback_state(
    payload: PlaybackStateUpdateRequest,
    session: AsyncSession = Depends(db_session),
) -> PlaybackStateResponse:
    await _ensure_tracks_exist(
        session,
        [track_id for track_id in [payload.current_track_id, *payload.queue_track_ids] if track_id],
    )

    state = await session.get(PlaybackState, DEFAULT_STATE_ID)
    now = utcnow()
    if state is None:
        state = PlaybackState(id=DEFAULT_STATE_ID, updated_at=now)
        session.add(state)

    state.current_track_id = payload.current_track_id
    state.position_seconds = payload.position_seconds
    state.is_playing = payload.is_playing
    state.repeat_mode = payload.repeat_mode
    state.shuffle = payload.shuffle
    state.active_device_id = payload.active_device_id
    state.active_device_name = payload.active_device_name
    state.updated_at = now

    await session.execute(
        delete(PlaybackQueueItem).where(PlaybackQueueItem.state_id == DEFAULT_STATE_ID)
    )
    for position, track_id in enumerate(payload.queue_track_ids, start=1):
        session.add(
            PlaybackQueueItem(
                state_id=DEFAULT_STATE_ID,
                track_id=track_id,
                position=position,
                added_at=now,
            )
        )

    await session.commit()
    return PlaybackStateResponse(**await _load_state_payload(session))


@router.delete("/state", status_code=status.HTTP_204_NO_CONTENT)
async def clear_playback_state(
    session: AsyncSession = Depends(db_session),
) -> None:
    await session.execute(delete(PlaybackQueueItem).where(PlaybackQueueItem.state_id == DEFAULT_STATE_ID))
    await session.execute(delete(PlaybackState).where(PlaybackState.id == DEFAULT_STATE_ID))
    await session.commit()


async def _load_state_payload(session: AsyncSession) -> dict[str, object]:
    state = await session.get(PlaybackState, DEFAULT_STATE_ID)
    if state is None:
        return {
            "current_track": None,
            "position_seconds": 0.0,
            "is_playing": False,
            "repeat_mode": "off",
            "shuffle": False,
            "active_device_id": None,
            "active_device_name": None,
            "queue": [],
            "updated_at": None,
        }

    current_track = None
    if state.current_track_id is not None:
        current_track_model = await session.get(Track, state.current_track_id)
        if current_track_model is not None:
            current_track = current_track_model.to_dict()

    queue_rows = await session.execute(
        select(PlaybackQueueItem, Track)
        .join(Track, Track.id == PlaybackQueueItem.track_id)
        .where(PlaybackQueueItem.state_id == DEFAULT_STATE_ID)
        .order_by(PlaybackQueueItem.position)
    )

    return {
        "current_track": current_track,
        "position_seconds": state.position_seconds,
        "is_playing": state.is_playing,
        "repeat_mode": state.repeat_mode,
        "shuffle": state.shuffle,
        "active_device_id": state.active_device_id,
        "active_device_name": state.active_device_name,
        "queue": [
            {
                "position": queue_item.position,
                "added_at": queue_item.added_at,
                "track": track.to_dict(),
            }
            for queue_item, track in queue_rows
        ],
        "updated_at": state.updated_at,
    }


async def _ensure_tracks_exist(session: AsyncSession, track_ids: list[UUID]) -> None:
    unique_ids = set(track_ids)
    if not unique_ids:
        return

    existing_ids = set(
        await session.scalars(select(Track.id).where(Track.id.in_(unique_ids)))
    )
    missing_ids = sorted(str(track_id) for track_id in unique_ids - existing_ids)
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track not found: {', '.join(missing_ids)}",
        )


async def clear_deleted_track_from_playback(session: AsyncSession, track_id: UUID) -> None:
    await session.execute(delete(PlaybackQueueItem).where(PlaybackQueueItem.track_id == track_id))
    await session.execute(
        update(PlaybackState)
        .where(PlaybackState.current_track_id == track_id)
        .values(
            current_track_id=None,
            position_seconds=0.0,
            is_playing=False,
            updated_at=utcnow(),
        )
    )
