from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.runtime import prepare_runtime
from app.db.models import ImportJob, Track, utcnow
from app.db.session import AsyncSessionLocal, init_db
from app.downloads.qbittorrent import QBittorrentDownloader
from app.imports.domain import ImportStatus
from app.library.audio import is_allowed_audio_file, scan_audio_file
from app.storage.library import LibraryStorage, build_library_storage


class TorrentStatusMismatch(RuntimeError):
    pass


async def run_once() -> None:
    prepare_runtime(settings)
    await init_db()
    await process_pending()


async def run_forever() -> None:
    prepare_runtime(settings)
    await init_db()
    while True:
        await process_pending()
        await asyncio.sleep(settings.import_worker_interval_seconds)


async def process_pending() -> None:
    storage = build_library_storage(settings)
    torrent_client = QBittorrentDownloader.from_settings(settings)
    async with AsyncSessionLocal() as session:
        jobs = await session.scalars(select(ImportJob).where(ImportJob.status.in_(ImportStatus.active())))
        for job in jobs:
            await process_downloaded_job_safely(job, session, storage, torrent_client)
        await session.commit()


async def process_downloaded_job_safely(
    job: ImportJob,
    session,
    storage: LibraryStorage,
    torrent_client,
) -> None:
    try:
        torrent_status = await torrent_client.status_by_label(f"mekamb-music:{job.id}")
    except Exception as exc:
        job.error_message = f"Could not read torrent client status: {exc}"
        job.updated_at = utcnow()
        return

    if torrent_status is None:
        job.status = ImportStatus.QUEUED.value
        job.error_message = "Torrent is not visible in qBittorrent yet."
        job.updated_at = utcnow()
        return

    if not torrent_status.is_complete:
        job.status = ImportStatus.DOWNLOADING.value
        job.error_message = None
        job.updated_at = utcnow()
        return

    try:
        validate_torrent_status_for_job(job, torrent_status)
    except TorrentStatusMismatch as exc:
        job.status = ImportStatus.FAILED.value
        job.error_message = str(exc)
        job.updated_at = utcnow()
        return

    job.status = ImportStatus.READY_TO_IMPORT.value
    job.error_message = None
    job.updated_at = utcnow()
    await process_job_safely(job, session, storage)


async def process_job_safely(job: ImportJob, session, storage: LibraryStorage) -> None:
    try:
        await process_job(job, session, storage)
    except Exception as exc:
        job.status = ImportStatus.FAILED.value
        job.error_message = str(exc)
        job.updated_at = utcnow()


async def process_job(job: ImportJob, session, storage: LibraryStorage) -> None:
    quarantine_path = Path(job.quarantine_path)
    if not quarantine_path.exists():
        return

    audio_files = [path for path in quarantine_path.rglob("*") if is_allowed_audio_file(path)]
    if not audio_files:
        return

    track_records: list[Track] = []
    for source in audio_files:
        metadata = scan_audio_file(source)
        storage_key = _storage_key(job.info_hash, source)
        storage.put_file(source, storage_key)
        track_records.append(
            Track(
                title=metadata.title,
                artist=metadata.artist,
                album=metadata.album,
                storage_key=storage_key,
                original_filename=source.name,
                media_type=metadata.media_type,
                codec=metadata.codec,
                duration_seconds=metadata.duration_seconds,
                size_bytes=metadata.size_bytes,
                source_import_id=job.id,
            )
        )

    for track in track_records:
        session.add(track)

    job.status = ImportStatus.IMPORTED.value
    job.updated_at = utcnow()


def _storage_key(info_hash: str, source: Path) -> str:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    return f"{info_hash.lower()}/{digest}-{source.name}"


def validate_torrent_status_for_job(job: ImportJob, torrent_status) -> None:
    expected_hash = job.info_hash.lower()
    actual_hash = torrent_status.info_hash.lower()
    if actual_hash != expected_hash:
        raise TorrentStatusMismatch(
            f"Torrent info_hash {torrent_status.info_hash!r} does not match import {job.info_hash!r}."
        )

    expected_save_path = (settings.torrent_download_root / str(job.id)).as_posix().rstrip("/")
    actual_save_path = Path(torrent_status.save_path).as_posix().rstrip("/")
    if actual_save_path != expected_save_path:
        raise TorrentStatusMismatch(
            f"Torrent save_path {torrent_status.save_path!r} does not match expected {expected_save_path!r}."
        )


if __name__ == "__main__":
    asyncio.run(run_forever())
