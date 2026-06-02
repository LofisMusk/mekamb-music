"""
Cache cleanup worker — usuwa tracki nieodtwarzane przez cache_ttl_days.
Usuwa też pliki audio, osierocone okładki i puste foldery.

Uruchamiany jako background asyncio task w FastAPI (run_cleanup_loop),
lub standalone: python -m app.workers.cache_cleanup
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import Track, utcnow
from app.db.session import AsyncSessionLocal, init_db
from app.library.streaming import InvalidLibraryPath, resolve_library_file

logger = logging.getLogger(__name__)


async def run_cleanup_once() -> dict[str, int | float]:
    """
    Jednorazowy cleanup. Zwraca statystyki.
    """
    cutoff = datetime.now(UTC) - timedelta(days=settings.cache_ttl_days)
    logger.info("Cache cleanup: cutoff = %s", cutoff.isoformat())

    deleted_tracks = 0
    freed_bytes = 0
    deleted_covers: set[str] = set()

    async with AsyncSessionLocal() as session:
        expired: list[Track] = list(
            await session.scalars(select(Track).where(Track.last_accessed < cutoff))
        )

        if not expired:
            logger.info("Cache cleanup: nic do usuniecia.")
            return {"deleted_tracks": 0, "freed_bytes": 0, "freed_mb": 0.0}

        cover_to_tracks: dict[str | None, list[UUID]] = defaultdict(list)
        for track in expired:
            cover_to_tracks[track.cover_key].append(track.id)

        for track in expired:
            try:
                path = resolve_library_file(settings.library_root, track.storage_key)
                if path.is_file():
                    freed_bytes += path.stat().st_size
                    path.unlink()
                    deleted_tracks += 1
            except (InvalidLibraryPath, OSError) as exc:
                logger.warning("Nie mozna usunac pliku %s: %s", track.storage_key, exc)

        # Sprawdz czy okładki sa teraz osierocone
        ids_being_deleted = {t.id for t in expired}
        for cover_key, ids_using_cover in cover_to_tracks.items():
            if cover_key is None:
                continue
            still_alive = await session.scalar(
                select(func.count(Track.id)).where(
                    Track.cover_key == cover_key,
                    Track.id.not_in(ids_being_deleted),
                    Track.last_accessed >= cutoff,
                )
            )
            if still_alive == 0:
                _delete_cover_file(cover_key)
                deleted_covers.add(cover_key)

        await session.commit()

    freed_mb = round(freed_bytes / 1024 / 1024, 2)
    logger.info(
        "Cache cleanup: %d tracks, %d covers, %.1f MB freed.",
        deleted_tracks, len(deleted_covers), freed_mb,
    )
    return {"deleted_tracks": deleted_tracks, "freed_bytes": freed_bytes, "freed_mb": freed_mb}


async def run_cleanup_loop() -> None:
    """Nieskończona pętla — uruchamiana jako FastAPI background task."""
    while True:
        await asyncio.sleep(settings.cache_cleanup_interval_seconds)
        try:
            stats = await run_cleanup_once()
            logger.info("Cleanup loop stats: %s", stats)
        except Exception as exc:
            logger.error("Cache cleanup loop error: %s", exc, exc_info=True)


async def get_cache_stats() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        total_tracks = await session.scalar(select(func.count(Track.id))) or 0
        total_bytes = await session.scalar(select(func.sum(Track.size_bytes))) or 0
        cutoff = datetime.now(UTC) - timedelta(days=settings.cache_ttl_days)
        stale_tracks = await session.scalar(
            select(func.count(Track.id)).where(Track.last_accessed < cutoff)
        ) or 0

    return {
        "total_tracks": total_tracks,
        "total_size_mb": round((total_bytes or 0) / 1024 / 1024, 2),
        "stale_tracks": stale_tracks,
        "cache_ttl_days": settings.cache_ttl_days,
        "library_root": str(settings.library_root),
    }


def _delete_cover_file(cover_key: str) -> None:
    try:
        path = resolve_library_file(settings.library_root, cover_key)
        if path.is_file():
            path.unlink()
    except (InvalidLibraryPath, OSError) as exc:
        logger.warning("Nie mozna usunac okładki %s: %s", cover_key, exc)


async def _main() -> None:
    await init_db()
    stats = await run_cleanup_once()
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
