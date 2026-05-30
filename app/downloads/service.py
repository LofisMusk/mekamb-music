from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.downloads.domain import DownloadStatus, TorrentRuntimeStatus
from app.imports.domain import ImportRepository


class TorrentStatusClient(Protocol):
    async def status_by_label(self, label: str) -> TorrentRuntimeStatus | None:
        ...


class DownloadService:
    def __init__(self, *, repository: ImportRepository, torrent_client: TorrentStatusClient) -> None:
        self.repository = repository
        self.torrent_client = torrent_client

    async def get_download_status(self, import_id: UUID) -> DownloadStatus:
        record = await self.repository.get(import_id)
        torrent = await self.torrent_client.status_by_label(f"mekamb-music:{import_id}")
        return DownloadStatus(import_record=record, torrent=torrent)

