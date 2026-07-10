from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2, copytree, rmtree
from typing import Protocol
from uuid import UUID, uuid4

from app.imports.domain import ImportRecord, ImportRepository, ImportStatus

logger = logging.getLogger(__name__)


class InvalidImportCandidate(RuntimeError):
    pass


class SandboxViolation(RuntimeError):
    pass


class ImportNotRetryable(RuntimeError):
    pass


class ImportEventPublisher(Protocol):
    async def notify_import_changed(self, import_id: UUID) -> None:
        ...


class NoopImportEventPublisher:
    async def notify_import_changed(self, import_id: UUID) -> None:
        return None


@dataclass(frozen=True)
class QuarantinePlan:
    import_id: UUID
    host_path: Path


class QuarantinePlanner:
    def __init__(
        self,
        *,
        quarantine_root: Path,
        library_root: Path,
    ) -> None:
        self.quarantine_root = quarantine_root
        self.library_root = library_root

    def plan(self, import_id: UUID) -> QuarantinePlan:
        host_root = self.quarantine_root.resolve()
        library_root = self.library_root.resolve()
        host_path = (host_root / str(import_id)).resolve()

        if host_path == library_root or library_root in host_path.parents:
            raise SandboxViolation("Quarantine path must not be inside the library path.")
        if host_root not in host_path.parents:
            raise SandboxViolation("Quarantine path escaped the configured quarantine root.")

        return QuarantinePlan(import_id=import_id, host_path=host_path)


class ImportService:
    """Owns ingest job records. Downloading/organizing is done by Lidarr; this
    service materializes Lidarr's finished album into quarantine and hands it to
    the worker, which runs the existing audio-validation → library pipeline."""

    def __init__(
        self,
        *,
        repository: ImportRepository,
        planner: QuarantinePlanner,
        ingest_strategy: str = "copy",
        event_publisher: ImportEventPublisher | None = None,
    ) -> None:
        self.repository = repository
        self.planner = planner
        self.ingest_strategy = ingest_strategy
        self.event_publisher = event_publisher or NoopImportEventPublisher()

    @classmethod
    def from_settings(
        cls,
        settings: object,
        *,
        repository: ImportRepository,
        event_publisher: ImportEventPublisher | None = None,
    ) -> "ImportService":
        planner = QuarantinePlanner(
            quarantine_root=getattr(settings, "quarantine_root"),
            library_root=getattr(settings, "library_root"),
        )
        return cls(
            repository=repository,
            planner=planner,
            ingest_strategy=getattr(settings, "lidarr_ingest_strategy", "copy"),
            event_publisher=event_publisher,
        )

    async def create_lidarr_import(
        self,
        *,
        source_dir: Path,
        foreign_key: str,
        name: str,
        source_url: str = "lidarr",
    ) -> ImportRecord:
        """Materialize a Lidarr-imported album folder into quarantine and queue
        it for ingest. ``foreign_key`` (e.g. the Lidarr album/release id) doubles
        as the storage-key namespace, replacing a torrent info_hash."""
        source_dir = Path(source_dir)
        if not source_dir.exists() or not source_dir.is_dir():
            raise InvalidImportCandidate(f"Lidarr import path {source_dir} is not a directory.")
        info_hash = _normalize_key(foreign_key)
        if not info_hash:
            raise InvalidImportCandidate("Lidarr import is missing an identifier.")

        existing = await self.repository.get_by_info_hash(info_hash)
        if existing is not None:
            return existing

        import_id = uuid4()
        quarantine = self.planner.plan(import_id)
        quarantine.host_path.mkdir(parents=True, exist_ok=True)
        _materialize(source_dir, quarantine.host_path, strategy=self.ingest_strategy)

        now = datetime.now(UTC)
        record = ImportRecord(
            id=import_id,
            source="lidarr",
            torrent_id=info_hash,
            info_hash=info_hash,
            magnet_link="",
            uploader="lidarr",
            source_url=source_url or "lidarr",
            status=ImportStatus.READY_TO_IMPORT.value,
            quarantine_path=str(quarantine.host_path),
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        record = await self.repository.add(record)
        await self._notify_import_changed(record.id)
        return record

    async def get_import(self, import_id: UUID) -> ImportRecord:
        return await self.repository.get(import_id)

    async def cancel_import(self, import_id: UUID, *, delete_files: bool = True) -> ImportRecord:
        record = await self.repository.get(import_id)
        if delete_files:
            self._remove_quarantine_path(record.quarantine_path)

        record.status = ImportStatus.CANCELED.value
        record.error_message = None
        record.updated_at = datetime.now(UTC)
        record = await self.repository.update(record)
        await self._notify_import_changed(record.id)
        return record

    async def retry_import(self, import_id: UUID, *, delete_files: bool = False) -> ImportRecord:
        record = await self.repository.get(import_id)
        if record.status in ImportStatus.active():
            raise ImportNotRetryable("Import is already active.")
        if record.status == ImportStatus.IMPORTED.value:
            raise ImportNotRetryable("Imported records cannot be retried.")

        quarantine_path = Path(record.quarantine_path)
        if not quarantine_path.exists():
            raise ImportNotRetryable(
                "Quarantine files are gone; re-add the artist/album through the catalog."
            )

        record.status = ImportStatus.READY_TO_IMPORT.value
        record.error_message = None
        record.updated_at = datetime.now(UTC)
        record = await self.repository.update(record)
        await self._notify_import_changed(record.id)
        return record

    async def list_imports(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImportRecord]:
        return await self.repository.list(status=status, limit=limit, offset=offset)

    def _remove_quarantine_path(self, quarantine_path: str) -> None:
        path = Path(quarantine_path).resolve()
        root = self.planner.quarantine_root.resolve()
        if path == root or root not in path.parents:
            raise SandboxViolation("Refusing to remove a path outside the quarantine root.")
        if path.exists():
            rmtree(path)

    async def _notify_import_changed(self, import_id: UUID) -> None:
        try:
            await self.event_publisher.notify_import_changed(import_id)
        except Exception as exc:
            logger.warning("Could not publish import event for %s: %s", import_id, exc)


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in str(value).strip() if ch.isalnum() or ch in "-_:.").strip()


def _materialize(source_dir: Path, dest_dir: Path, *, strategy: str) -> None:
    """Copy (or hardlink) the album files from Lidarr's output into quarantine.
    Hardlinking avoids duplicating large lossless files when both roots live on
    the same filesystem; it falls back to a copy across devices."""
    for root, _dirs, files in os.walk(source_dir):
        rel_root = Path(root).relative_to(source_dir)
        target_root = dest_dir / rel_root
        target_root.mkdir(parents=True, exist_ok=True)
        for filename in files:
            src = Path(root) / filename
            dst = target_root / filename
            if dst.exists():
                continue
            if strategy == "hardlink":
                try:
                    os.link(src, dst)
                    continue
                except OSError:
                    pass
            copy2(src, dst)
