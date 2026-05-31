from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from typing import Protocol
from uuid import UUID, uuid4

from app.imports.domain import ImportRecord, ImportRepository, ImportStatus
from app.sources.personal_1337x import Personal1337xImportCandidate
from app.sources.piratebay import PirateBayImportCandidate

logger = logging.getLogger(__name__)


class InvalidImportCandidate(RuntimeError):
    pass


class SandboxViolation(RuntimeError):
    pass


class ImportNotRetryable(RuntimeError):
    pass


class TorrentDownloader(Protocol):
    async def enqueue(self, *, magnet_link: str, download_path: Path, label: str) -> None:
        ...

    async def delete_by_label(self, label: str, *, delete_files: bool) -> bool:
        ...


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
    torrent_path: Path


class QuarantinePlanner:
    def __init__(
        self,
        *,
        quarantine_root: Path,
        torrent_download_root: Path,
        library_root: Path,
    ) -> None:
        self.quarantine_root = quarantine_root
        self.torrent_download_root = torrent_download_root
        self.library_root = library_root

    def plan(self, import_id: UUID) -> QuarantinePlan:
        host_root = self.quarantine_root.resolve()
        library_root = self.library_root.resolve()
        host_path = (host_root / str(import_id)).resolve()

        if host_path == library_root or library_root in host_path.parents:
            raise SandboxViolation("Quarantine path must not be inside the library path.")
        if host_root not in host_path.parents:
            raise SandboxViolation("Quarantine path escaped the configured quarantine root.")

        torrent_path = self.torrent_download_root / str(import_id)
        return QuarantinePlan(import_id=import_id, host_path=host_path, torrent_path=torrent_path)


class ImportService:
    def __init__(
        self,
        *,
        repository: ImportRepository,
        downloader: TorrentDownloader,
        planner: QuarantinePlanner,
        event_publisher: ImportEventPublisher | None = None,
    ) -> None:
        self.repository = repository
        self.downloader = downloader
        self.planner = planner
        self.event_publisher = event_publisher or NoopImportEventPublisher()

    @classmethod
    def from_settings(
        cls,
        settings: object,
        *,
        repository: ImportRepository,
        downloader: TorrentDownloader,
        event_publisher: ImportEventPublisher | None = None,
    ) -> "ImportService":
        planner = QuarantinePlanner(
            quarantine_root=getattr(settings, "quarantine_root"),
            torrent_download_root=getattr(settings, "torrent_download_root"),
            library_root=getattr(settings, "library_root"),
        )
        return cls(
            repository=repository,
            downloader=downloader,
            planner=planner,
            event_publisher=event_publisher,
        )

    async def create_1337x_import(self, candidate: Personal1337xImportCandidate) -> ImportRecord:
        return await self._create_torrent_import(candidate, source="personal_1337x")

    async def create_piratebay_import(self, candidate: PirateBayImportCandidate) -> ImportRecord:
        return await self._create_torrent_import(candidate, source="piratebay_pmedia")

    async def _create_torrent_import(
        self,
        candidate: Personal1337xImportCandidate | PirateBayImportCandidate,
        *,
        source: str,
    ) -> ImportRecord:
        self._validate_candidate(candidate)

        existing = await self.repository.get_by_info_hash(candidate.info_hash)
        if existing is not None:
            return existing

        import_id = uuid4()
        quarantine = self.planner.plan(import_id)
        quarantine.host_path.mkdir(parents=True, exist_ok=True)

        now = datetime.now(UTC)
        record = ImportRecord(
            id=import_id,
            source=source,
            torrent_id=candidate.torrent_id,
            info_hash=candidate.info_hash,
            magnet_link=candidate.magnet_link,
            uploader=candidate.uploader,
            source_url=candidate.source_url,
            status=ImportStatus.QUEUED.value,
            quarantine_path=str(quarantine.host_path),
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        await self.downloader.enqueue(
            magnet_link=candidate.magnet_link,
            download_path=quarantine.torrent_path,
            label=f"mekamb-music:{import_id}",
        )
        record = await self.repository.add(record)
        await self._notify_import_changed(record.id)
        return record

    async def get_import(self, import_id: UUID) -> ImportRecord:
        return await self.repository.get(import_id)

    async def cancel_import(self, import_id: UUID, *, delete_files: bool = True) -> ImportRecord:
        record = await self.repository.get(import_id)
        removed_from_client = await self.downloader.delete_by_label(
            f"mekamb-music:{import_id}",
            delete_files=delete_files,
        )
        if delete_files:
            self._remove_quarantine_path(record.quarantine_path)

        now = datetime.now(UTC)
        record.status = ImportStatus.CANCELED.value
        record.error_message = (
            None if removed_from_client else "Torrent was not visible in qBittorrent."
        )
        record.updated_at = now
        record = await self.repository.update(record)
        await self._notify_import_changed(record.id)
        return record

    async def retry_import(self, import_id: UUID, *, delete_files: bool = True) -> ImportRecord:
        record = await self.repository.get(import_id)
        if record.status in ImportStatus.active():
            raise ImportNotRetryable("Import is already active.")
        if record.status == ImportStatus.IMPORTED.value:
            raise ImportNotRetryable("Imported records cannot be retried.")

        await self.downloader.delete_by_label(
            f"mekamb-music:{import_id}",
            delete_files=delete_files,
        )
        quarantine = self.planner.plan(import_id)
        if delete_files:
            self._remove_quarantine_path(str(quarantine.host_path))
        quarantine.host_path.mkdir(parents=True, exist_ok=True)

        await self.downloader.enqueue(
            magnet_link=record.magnet_link,
            download_path=quarantine.torrent_path,
            label=f"mekamb-music:{import_id}",
        )

        record.status = ImportStatus.QUEUED.value
        record.quarantine_path = str(quarantine.host_path)
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

    def _validate_candidate(self, candidate: Personal1337xImportCandidate) -> None:
        if not candidate.magnet_link:
            raise InvalidImportCandidate("Import candidate has no magnet link.")
        if not candidate.info_hash:
            raise InvalidImportCandidate("Import candidate has no info hash.")
        if not candidate.uploader:
            raise InvalidImportCandidate("Import candidate has no uploader.")
        if not candidate.source_url:
            raise InvalidImportCandidate("Import candidate has no source URL.")

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
