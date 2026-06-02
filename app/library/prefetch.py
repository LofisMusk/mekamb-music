from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select, update

from app.core.config import settings
from app.db.models import PlaybackQueueItem, Track, utcnow
from app.db.session import AsyncSessionLocal
from app.storage.library import build_library_storage

logger = logging.getLogger(__name__)


async def prefetch_tracks(track_ids: list[UUID], *, limit: int | None = None) -> None:
    selected_ids = _dedupe(track_ids)
    if limit is not None:
        selected_ids = selected_ids[: max(0, limit)]
    if not selected_ids:
        return

    async with AsyncSessionLocal() as session:
        tracks = list(await session.scalars(select(Track).where(Track.id.in_(selected_ids))))
        by_id = {track.id: track for track in tracks}
        ordered_tracks = [by_id[track_id] for track_id in selected_ids if track_id in by_id]

    results = await asyncio.gather(
        *[asyncio.to_thread(_ensure_track_cached, track) for track in ordered_tracks],
        return_exceptions=True,
    )
    cached_track_ids = [
        track.id
        for track, result in zip(ordered_tracks, results, strict=False)
        if not isinstance(result, Exception)
    ]
    await touch_prefetched_tracks(cached_track_ids)


async def prefetch_next_queue_tracks(*, limit: int | None = None) -> None:
    prefetch_limit = settings.playback_prefetch_count if limit is None else limit
    async with AsyncSessionLocal() as session:
        track_ids = list(
            await session.scalars(
                select(PlaybackQueueItem.track_id)
                .where(PlaybackQueueItem.state_id == "default")
                .order_by(PlaybackQueueItem.position)
                .limit(max(0, prefetch_limit))
            )
        )
    await prefetch_tracks(track_ids, limit=prefetch_limit)


def _ensure_track_cached(track: Track) -> None:
    try:
        storage = build_library_storage(settings)
        storage.ensure_cached(track.storage_key)
    except Exception as exc:
        logger.warning("Could not prefetch track %s (%s): %s", track.id, track.storage_key, exc)
        raise


async def touch_prefetched_tracks(track_ids: list[UUID]) -> None:
    selected_ids = _dedupe(track_ids)
    if not selected_ids:
        return
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Track).where(Track.id.in_(selected_ids)).values(last_accessed=utcnow())
        )
        await session.commit()


def _dedupe(track_ids: list[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    deduped: list[UUID] = []
    for track_id in track_ids:
        if track_id in seen:
            continue
        seen.add(track_id)
        deduped.append(track_id)
    return deduped
