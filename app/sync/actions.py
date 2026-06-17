from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import DEFAULT_API_KEY_ID
from app.core.config import settings
from app.db.models import (
    LikedTrack,
    PersonalizationSignal,
    PlaybackQueueItem,
    PlaybackState,
    PlaylistTrack,
    Track,
    TrackPlay,
    UserAction,
    utcnow,
)
from app.imports.service import ImportService
from app.storage.library import build_library_storage


IMPORT_TORRENT = "import_torrent"
LIKE_TRACK = "like_track"
UNLIKE_TRACK = "unlike_track"
DELETE_TRACK = "delete_track"


@dataclass(frozen=True)
class SyncTorrentCandidate:
    torrent_id: str
    info_hash: str
    magnet_link: str
    uploader: str
    source_url: str


async def record_user_action(
    session: AsyncSession,
    *,
    action_type: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict[str, Any],
    action_id: UUID | None = None,
    origin_instance_id: str | None = None,
    api_key_id: str = DEFAULT_API_KEY_ID,
    created_at: datetime | None = None,
    applied: bool = True,
) -> UserAction:
    action = UserAction(
        id=action_id or uuid4(),
        api_key_id=api_key_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        origin_instance_id=origin_instance_id or settings.instance_id,
        created_at=created_at or datetime.now(UTC),
        applied_at=datetime.now(UTC) if applied else None,
    )
    session.add(action)
    await session.commit()
    await session.refresh(action)
    return action


async def merge_remote_action(
    session: AsyncSession,
    *,
    action_id: UUID,
    action_type: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict[str, Any],
    origin_instance_id: str,
    api_key_id: str = DEFAULT_API_KEY_ID,
    created_at: datetime,
) -> UserAction:
    existing = await session.get(UserAction, action_id)
    if existing is not None:
        return existing
    return await record_user_action(
        session,
        action_id=action_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        origin_instance_id=origin_instance_id,
        api_key_id=api_key_id,
        created_at=created_at,
        applied=origin_instance_id == settings.instance_id,
    )


async def list_actions(
    session: AsyncSession,
    *,
    api_key_id: str = DEFAULT_API_KEY_ID,
    since: datetime | None,
    limit: int,
    include_applied: bool,
) -> list[UserAction]:
    statement = (
        select(UserAction)
        .where(UserAction.api_key_id == api_key_id)
        .order_by(UserAction.created_at.asc())
        .limit(limit)
    )
    if since is not None:
        statement = statement.where(UserAction.created_at > since)
    if not include_applied:
        statement = statement.where(UserAction.applied_at.is_(None))
    actions = await session.scalars(statement)
    return list(actions)


async def apply_action(
    session: AsyncSession,
    action: UserAction,
    *,
    import_service: ImportService,
) -> UserAction:
    try:
        if action.applied_at is not None:
            return action
        await _apply_action(session, action, import_service=import_service)
        action.applied_at = datetime.now(UTC)
        action.apply_error = None
    except Exception as exc:
        action.apply_error = str(exc)
    await session.commit()
    await session.refresh(action)
    return action


async def _apply_action(
    session: AsyncSession,
    action: UserAction,
    *,
    import_service: ImportService,
) -> None:
    if action.action_type == IMPORT_TORRENT:
        await _apply_import_torrent(action, import_service=import_service)
        return
    if action.action_type == LIKE_TRACK:
        await _apply_like_track(session, action)
        return
    if action.action_type == UNLIKE_TRACK:
        await _apply_unlike_track(session, action)
        return
    if action.action_type == DELETE_TRACK:
        await _apply_delete_track(session, action)
        return
    raise ValueError(f"Unsupported sync action {action.action_type!r}.")


async def _apply_import_torrent(
    action: UserAction,
    *,
    import_service: ImportService,
) -> None:
    payload = action.payload
    source = _payload_text(payload, "source", "synced_torrent")
    candidate = SyncTorrentCandidate(
        torrent_id=_payload_text(payload, "torrent_id"),
        info_hash=_payload_text(payload, "info_hash"),
        magnet_link=_payload_text(payload, "magnet_link"),
        uploader=_payload_text(payload, "uploader", "synced"),
        source_url=_payload_text(payload, "source_url", "sync://user-action"),
    )
    await import_service.create_synced_torrent_import(candidate, source=source)


async def _apply_like_track(session: AsyncSession, action: UserAction) -> None:
    track_id = _track_id_from_action(action)
    track = await session.get(Track, track_id)
    if track is None:
        raise ValueError(f"Track {track_id} is not present on this instance yet.")
    liked = await session.scalar(
        select(LikedTrack).where(
            LikedTrack.api_key_id == action.api_key_id,
            LikedTrack.track_id == track_id,
        )
    )
    if liked is None:
        session.add(LikedTrack(api_key_id=action.api_key_id, track_id=track_id))
        session.add(
            PersonalizationSignal(
                api_key_id=action.api_key_id,
                track_id=track_id,
                signal_type="like",
                weight=4.0,
                source="sync",
                payload={"track_title": track.title, "artist": track.artist, "album": track.album},
            )
        )


async def _apply_unlike_track(session: AsyncSession, action: UserAction) -> None:
    track_id = _track_id_from_action(action)
    await session.execute(
        delete(LikedTrack).where(
            LikedTrack.api_key_id == action.api_key_id,
            LikedTrack.track_id == track_id,
        )
    )
    track = await session.get(Track, track_id)
    if track is not None:
        session.add(
            PersonalizationSignal(
                api_key_id=action.api_key_id,
                track_id=track_id,
                signal_type="unlike",
                weight=-2.0,
                source="sync",
                payload={"track_title": track.title, "artist": track.artist, "album": track.album},
            )
        )


async def _apply_delete_track(session: AsyncSession, action: UserAction) -> None:
    track_id = _track_id_from_action(action)
    track = await session.get(Track, track_id)
    if track is not None:
        _delete_storage_key(track.storage_key)
        await session.execute(delete(PlaylistTrack).where(PlaylistTrack.track_id == track_id))
        await session.execute(delete(LikedTrack).where(LikedTrack.track_id == track_id))
        await session.execute(delete(TrackPlay).where(TrackPlay.track_id == track_id))
        await session.execute(delete(PersonalizationSignal).where(PersonalizationSignal.track_id == track_id))
        await session.execute(delete(PlaybackQueueItem).where(PlaybackQueueItem.track_id == track_id))
        await session.execute(
            update(PlaybackState)
            .where(PlaybackState.current_track_id == track_id)
            .values(current_track_id=None, position_seconds=0.0, is_playing=False, updated_at=utcnow())
        )
        await session.delete(track)
        return

    storage_key = action.payload.get("storage_key")
    if storage_key:
        _delete_storage_key(str(storage_key))


def import_action_payload(record: object) -> dict[str, Any]:
    return {
        "source": getattr(record, "source"),
        "torrent_id": getattr(record, "torrent_id"),
        "info_hash": getattr(record, "info_hash"),
        "magnet_link": getattr(record, "magnet_link"),
        "uploader": getattr(record, "uploader"),
        "source_url": getattr(record, "source_url"),
        "sync_strategy": ["peer_copy", "remote_storage", "magnet"],
    }


def track_action_payload(track: Track) -> dict[str, Any]:
    return {
        "track_id": str(track.id),
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "storage_key": track.storage_key,
        "source_import_id": str(track.source_import_id) if track.source_import_id else None,
    }


def _track_id_from_action(action: UserAction) -> UUID:
    payload_id = action.payload.get("track_id")
    track_id = payload_id or action.entity_id
    if not track_id:
        raise ValueError("Action has no track id.")
    return UUID(str(track_id))


def _payload_text(payload: dict[str, Any], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _delete_storage_key(storage_key: str) -> None:
    try:
        build_library_storage(settings).delete_file(storage_key)
    except FileNotFoundError:
        return
