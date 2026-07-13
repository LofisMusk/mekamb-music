"""Reconcile Lidarr's imported albums into the app catalog.

Lidarr's Manual Import (used by the IA backfill) does not fire the Connect
webhook, so albums land in Lidarr's root folder but never reach the app. This
module bridges that gap generically: given a Lidarr album, it fetches the exact
track-file paths (Lidarr dumps every album of an artist into one flat folder, so
a directory copy would mix albums — we name the files instead) and hands them to
the normal quarantine→library ingest pipeline. Idempotent per album.

Used two ways:
  * ``ingest_lidarr_album`` — called by the backfill right after a successful
    import, for immediacy (with a short wait for Lidarr to finish moving files);
  * ``run_library_reconcile_loop`` — a periodic safety net that catches every
    album with files, no matter how it got into Lidarr.
"""
from __future__ import annotations

import asyncio
import logging

from app.catalog.lidarr_client import LidarrClient, LidarrError
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.imports.queue import RedisImportQueue
from app.imports.repository import SqlAlchemyImportRepository
from app.imports.service import ImportService, _normalize_key

logger = logging.getLogger(__name__)


def _foreign_key(album: dict) -> str:
    return f"lidarr:{album.get('foreignAlbumId') or album.get('id')}"


def _album_name(album: dict) -> str:
    artist = (album.get("artist") or {}).get("artistName") or ""
    title = album.get("title") or ""
    return f"{artist} - {title}".strip(" -") or "Lidarr import"


async def ingest_lidarr_album(
    lidarr: LidarrClient,
    album: dict,
    *,
    publisher: RedisImportQueue,
    wait_seconds: float = 0.0,
) -> str:
    """Ingest one Lidarr album's track files into the app. Returns "ingested",
    "exists" (already had an import record), or "pending" (Lidarr has no files on
    disk yet). ``wait_seconds`` briefly polls for files Lidarr is still moving."""
    album_id = album.get("id")
    if not album_id:
        return "pending"

    deadline_tries = max(1, int(wait_seconds // 2) + 1)
    paths: list[str] = []
    for attempt in range(deadline_tries):
        track_files = await asyncio.to_thread(lidarr.album_track_files, int(album_id))
        paths = [str(tf["path"]) for tf in track_files if tf.get("path")]
        if paths or attempt == deadline_tries - 1:
            break
        await asyncio.sleep(2)
    if not paths:
        return "pending"

    async with AsyncSessionLocal() as session:
        service = ImportService.from_settings(
            settings,
            repository=SqlAlchemyImportRepository(session),
            event_publisher=publisher,
        )
        existed = await service.repository.get_by_info_hash(_normalize_key(_foreign_key(album)))
        record = await service.create_lidarr_import_from_files(
            files=paths, foreign_key=_foreign_key(album), name=_album_name(album)
        )
        await session.commit()
    if record is None:
        return "pending"
    return "exists" if existed is not None else "ingested"


async def run_library_reconcile_once() -> int:
    """Ingest every Lidarr album that has track files but no app import yet.
    Returns how many were newly ingested."""
    lidarr = LidarrClient.from_settings(settings)
    if not lidarr.configured:
        return 0
    try:
        albums = await asyncio.to_thread(lidarr.all_albums)
    except LidarrError as exc:
        logger.warning("library-reconcile: could not list albums: %s", exc)
        return 0

    publisher = RedisImportQueue.from_settings(settings)
    ingested = 0
    try:
        for album in albums:
            if ((album.get("statistics") or {}).get("trackFileCount") or 0) <= 0:
                continue
            try:
                result = await ingest_lidarr_album(lidarr, album, publisher=publisher)
                if result == "ingested":
                    ingested += 1
                    logger.info("library-reconcile: ingested %s into the app", _album_name(album))
            except Exception:
                logger.exception("library-reconcile: failed to ingest album %s", album.get("id"))
    finally:
        await publisher.close()
    return ingested


async def run_library_reconcile_loop() -> None:
    if not settings.library_reconcile_enabled:
        return
    while True:
        await asyncio.sleep(settings.library_reconcile_interval_seconds)
        try:
            ingested = await run_library_reconcile_once()
            if ingested:
                logger.info("library-reconcile loop: ingested %d album(s)", ingested)
        except Exception:
            logger.exception("library-reconcile loop error")
