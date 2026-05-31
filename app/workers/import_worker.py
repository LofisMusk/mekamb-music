from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
from pathlib import Path
from shutil import rmtree

from sqlalchemy import select

from app.core.config import settings
from app.core.runtime import prepare_runtime
from app.db.models import ImportJob, Track, utcnow
from app.db.session import AsyncSessionLocal, init_db
from app.downloads.qbittorrent import QBittorrentDownloader
from app.imports.domain import ImportStatus
from app.imports.queue import RedisImportQueue
from app.library.audio import extract_cover, is_allowed_audio_file, scan_audio_file
from app.storage.library import LibraryStorage, build_library_storage

logger = logging.getLogger(__name__)

_SENTINEL = Path("/tmp/worker-alive")


class TorrentStatusMismatch(RuntimeError):
    pass


class QuarantineImportViolation(RuntimeError):
    pass


async def run_once() -> None:
    prepare_runtime(settings)
    await init_db()
    await process_pending()


async def run_forever() -> None:
    prepare_runtime(settings)
    await init_db()
    queue = RedisImportQueue.from_settings(settings)
    try:
        while True:
            await process_pending()
            _SENTINEL.touch()
            try:
                await queue.wait_for_import_changed(
                    timeout_seconds=settings.import_worker_interval_seconds
                )
            except Exception as exc:
                logger.warning("Import queue unavailable, falling back to polling: %s", exc)
                await asyncio.sleep(settings.import_worker_interval_seconds)
    finally:
        await queue.close()


async def process_pending() -> None:
    storage = build_library_storage(settings)
    torrent_client = QBittorrentDownloader.from_settings(settings)
    async with AsyncSessionLocal() as session:
        jobs = await session.scalars(
            select(ImportJob).where(ImportJob.status.in_(ImportStatus.active()))
        )
        for job in jobs:
            await process_downloaded_job_safely(job, session, storage, torrent_client)
            await session.commit()
            if job.status == ImportStatus.IMPORTED.value:
                await cleanup_completed_import(job, torrent_client)
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
    quarantine_path = resolve_quarantine_path(job.quarantine_path)
    if not quarantine_path.exists():
        raise QuarantineImportViolation(f"Quarantine path {quarantine_path} does not exist.")
    if not quarantine_path.is_dir():
        raise QuarantineImportViolation(f"Quarantine path {quarantine_path} is not a directory.")

    audio_files = sorted(
        (path for path in quarantine_path.rglob("*") if is_allowed_audio_file(path)),
        key=lambda path: path.as_posix(),
    )
    if not audio_files:
        raise QuarantineImportViolation(
            "Downloaded torrent did not contain any supported audio files."
        )

    # Wyciągnij okładkę raz dla całego importu
    cover_key = _import_cover(audio_files, job.info_hash, storage)

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
                cover_key=cover_key,
                source_import_id=job.id,
            )
        )

    for track in track_records:
        session.add(track)

    job.status = ImportStatus.IMPORTED.value
    job.updated_at = utcnow()


def _import_cover(audio_files: list[Path], info_hash: str, storage: LibraryStorage) -> str | None:
    """Wyciągnij okładkę z pierwszego pliku który ją ma, zapisz w library."""
    for path in audio_files:
        result = extract_cover(path)
        if result is None:
            continue

        data, mime = result
        ext = mimetypes.guess_extension(mime) or ".jpg"
        if ext in (".jpe", ".jpeg"):
            ext = ".jpg"

        cover_key = f"{info_hash.lower()}/cover{ext}"
        tmp = path.parent / f"_cover_tmp{ext}"
        try:
            tmp.write_bytes(data)
            storage.put_file(tmp, cover_key)
        finally:
            tmp.unlink(missing_ok=True)

        return cover_key

    return None


async def cleanup_completed_import(job: ImportJob, torrent_client) -> None:
    errors: list[str] = []
    can_clean_quarantine = True
    if settings.remove_torrent_after_import:
        try:
            await torrent_client.delete_by_label(f"mekamb-music:{job.id}", delete_files=True)
        except Exception as exc:
            can_clean_quarantine = False
            errors.append(f"Could not remove torrent from qBittorrent: {exc}")

    if settings.cleanup_quarantine_after_import and can_clean_quarantine:
        try:
            remove_quarantine_path(job.quarantine_path)
        except Exception as exc:
            errors.append(f"Could not clean quarantine path: {exc}")

    if errors:
        job.error_message = "; ".join(errors)
        job.updated_at = utcnow()
        logger.warning("Import %s finished with cleanup warnings: %s", job.id, job.error_message)


def remove_quarantine_path(quarantine_path: str) -> None:
    path = resolve_quarantine_path(quarantine_path, action="remove")
    if path.exists():
        rmtree(path)


def resolve_quarantine_path(quarantine_path: str, *, action: str = "use") -> Path:
    path = Path(quarantine_path).expanduser().resolve()
    root = settings.quarantine_root.resolve()
    if path == root or root not in path.parents:
        raise QuarantineImportViolation(f"Refusing to {action} a path outside the quarantine root.")
    return path


def _storage_key(info_hash: str, source: Path) -> str:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    return f"{info_hash.lower()}/{digest}-{source.name}"


def validate_torrent_status_for_job(job: ImportJob, torrent_status) -> None:
    expected_hash = job.info_hash.lower()
    actual_hash = torrent_status.info_hash.lower()
    if actual_hash != expected_hash:
        raise TorrentStatusMismatch(
            f"Torrent info_hash {torrent_status.info_hash!r} "
            f"does not match import {job.info_hash!r}."
        )

    expected_save_path = (settings.torrent_download_root / str(job.id)).as_posix().rstrip("/")
    actual_save_path = Path(torrent_status.save_path).as_posix().rstrip("/")
    if actual_save_path != expected_save_path:
        raise TorrentStatusMismatch(
            f"Torrent save_path {torrent_status.save_path!r} "
            f"does not match expected {expected_save_path!r}."
        )


if __name__ == "__main__":
    asyncio.run(run_forever())
