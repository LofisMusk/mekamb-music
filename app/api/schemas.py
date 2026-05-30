from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PageBase(BaseModel):
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str


class ReadinessCheckResponse(BaseModel):
    name: str
    status: str
    detail: str


class ReadinessResponse(BaseModel):
    status: str
    checks: list[ReadinessCheckResponse]


class Source1337xItem(BaseModel):
    name: str
    torrent_id: str
    url: str
    seeders: str
    leechers: str
    size: str
    time: str
    uploader: str
    uploader_link: str
    discovered_at: datetime


class Source1337xSearchResponse(BaseModel):
    items: list[Source1337xItem]
    filtered_by_uploader: str


class ImportRecordResponse(BaseModel):
    id: UUID
    source: str
    torrent_id: str
    info_hash: str
    uploader: str
    source_url: str
    status: str
    quarantine_path: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ImportListResponse(PageBase):
    items: list[ImportRecordResponse]
    status: str | None


class TorrentRuntimeStatusResponse(BaseModel):
    name: str
    info_hash: str
    state: str
    progress: float = Field(ge=0.0)
    size_bytes: int
    downloaded_bytes: int
    download_speed_bytes: int
    eta_seconds: int
    save_path: str


class DownloadStatusResponse(BaseModel):
    import_record: ImportRecordResponse = Field(alias="import")
    torrent: TorrentRuntimeStatusResponse | None


class TrackResponse(BaseModel):
    id: UUID
    title: str
    artist: str | None
    album: str | None
    storage_key: str
    original_filename: str
    media_type: str | None
    codec: str | None
    duration_seconds: int | None
    size_bytes: int
    source_import_id: UUID | None
    created_at: datetime


class TrackListResponse(PageBase):
    items: list[TrackResponse]
    query: str | None


class ArtistSummaryResponse(BaseModel):
    name: str
    track_count: int
    latest_track_at: datetime | None


class ArtistListResponse(PageBase):
    items: list[ArtistSummaryResponse]
    query: str | None


class AlbumSummaryResponse(BaseModel):
    title: str
    artist: str
    track_count: int
    latest_track_at: datetime | None


class AlbumListResponse(PageBase):
    items: list[AlbumSummaryResponse]
    query: str | None
