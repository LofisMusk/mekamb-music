from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class ImportNotFound(RuntimeError):
    pass


class ImportStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    READY_TO_IMPORT = "ready_to_import"
    IMPORTED = "imported"
    FAILED = "failed"
    CANCELED = "canceled"

    @classmethod
    def active(cls) -> tuple[str, ...]:
        return (cls.QUEUED.value, cls.DOWNLOADING.value, cls.READY_TO_IMPORT.value)


@dataclass
class ImportRecord:
    id: UUID
    source: str
    torrent_id: str
    info_hash: str
    magnet_link: str
    uploader: str
    source_url: str
    status: str
    quarantine_path: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["id"] = str(self.id)
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


class ImportRepository(Protocol):
    async def add(self, record: ImportRecord) -> ImportRecord:
        ...

    async def get(self, import_id: UUID) -> ImportRecord:
        ...

    async def get_by_info_hash(self, info_hash: str) -> ImportRecord | None:
        ...

    async def list(self, *, status: str | None, limit: int, offset: int) -> list[ImportRecord]:
        ...

    async def update(self, record: ImportRecord) -> ImportRecord:
        ...
