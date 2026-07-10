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
from app.imports.domain import ImportStatus
from app.imports.queue import RedisImportQueue
from app.library.audio import (
    extract_cover,
    find_cover_image,
    is_allowed_audio_file,
    scan_audio_file,
)
from app.storage.library import LibraryStorage, build_library_storage

logger = logging.getLogger(__name__)

_SENTINEL = Path("/tmp/worker-alive")


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
    async with AsyncSessionLocal() as session:
        jobs = await session.scalars(
            select(ImportJob).where(ImportJob.status.in_(ImportStatus.active()))
        )
        for job in jobs:
            # Lidarr already downloaded + organized the album into quarantine, so
            # every active job is ready to ingest straight away.
            await process_job_safely(job, session, storage)
            await session.commit()
            if job.status == ImportStatus.IMPORTED.value:
                await cleanup_completed_import(job)
                await session.commit()


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
    cover_key = _import_cover(quarantine_path, audio_files, job.info_hash, storage)
    remove_non_audio_files(quarantine_path)

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


def _import_cover(
    quarantine_path: Path,
    audio_files: list[Path],
    info_hash: str,
    storage: LibraryStorage,
) -> str | None:
    cover_file = find_cover_image(quarantine_path)
    if cover_file is not None:
        ext = cover_file.suffix.lower() or ".jpg"
        cover_key = f"{_key_namespace(info_hash)}/cover{ext}"
        storage.put_file(cover_file, cover_key)
        return cover_key

    """Wyciągnij okładkę z pierwszego pliku który ją ma, zapisz w library."""
    for path in audio_files:
        result = extract_cover(path)
        if result is None:
            continue

        data, mime = result
        ext = mimetypes.guess_extension(mime) or ".jpg"
        if ext in (".jpe", ".jpeg"):
            ext = ".jpg"

        cover_key = f"{_key_namespace(info_hash)}/cover{ext}"
        tmp = path.parent / f"_cover_tmp{ext}"
        try:
            tmp.write_bytes(data)
            storage.put_file(tmp, cover_key)
        finally:
            tmp.unlink(missing_ok=True)

        return cover_key

    return None


async def cleanup_completed_import(job: ImportJob) -> None:
    if not settings.cleanup_quarantine_after_import:
        return
    try:
        remove_quarantine_path(job.quarantine_path)
    except Exception as exc:
        job.error_message = f"Could not clean quarantine path: {exc}"
        job.updated_at = utcnow()
        logger.warning("Import %s finished with cleanup warnings: %s", job.id, job.error_message)


def remove_quarantine_path(quarantine_path: str) -> None:
    path = resolve_quarantine_path(quarantine_path, action="remove")
    if path.exists():
        rmtree(path)


def remove_non_audio_files(quarantine_path: Path) -> None:
    for path in sorted(quarantine_path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file() and not is_allowed_audio_file(path):
            path.unlink()
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def resolve_quarantine_path(quarantine_path: str, *, action: str = "use") -> Path:
    path = Path(quarantine_path).expanduser().resolve()
    root = settings.quarantine_root.resolve()
    if path == root or root not in path.parents:
        raise QuarantineImportViolation(f"Refusing to {action} a path outside the quarantine root.")
    return path


def _storage_key(info_hash: str, source: Path) -> str:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    return f"{_key_namespace(info_hash)}/{digest}-{source.name}"


def _key_namespace(info_hash: str) -> str:
    # Lidarr keys look like "lidarr:123"; keep them filesystem-safe as a prefix.
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in info_hash.lower())


if __name__ == "__main__":
    asyncio.run(run_forever())
