from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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


class LibrarySummaryResponse(BaseModel):
    track_count: int
    artist_count: int
    album_count: int
    playlist_count: int
    liked_track_count: int
    playback_event_count: int
    import_count: int
    active_import_count: int
    failed_import_count: int
    library_size_bytes: int
    total_duration_seconds: int
    latest_track_at: datetime | None
    latest_import_at: datetime | None


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


class SourcePirateBayItem(BaseModel):
    name: str
    torrent_id: str
    info_hash: str
    magnet_link: str
    url: str
    seeders: str
    leechers: str
    size_bytes: int
    num_files: int
    uploader: str
    category: str
    status: str
    added_at: datetime | None
    discovered_at: datetime


class SourcePirateBaySearchResponse(BaseModel):
    items: list[SourcePirateBayItem]
    title_marker: str


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
    duration_seconds: float | None  # float — obsługuje pliki < 1s
    size_bytes: int
    cover_key: str | None = None
    source_import_id: UUID | None
    created_at: datetime
    last_accessed: datetime


class TrackListResponse(PageBase):
    items: list[TrackResponse]
    query: str | None
    artist: str | None = None
    album: str | None = None
    source_import_id: UUID | None = None


class LikedTrackResponse(BaseModel):
    track: TrackResponse
    liked_at: datetime


class LikedTrackListResponse(PageBase):
    items: list[LikedTrackResponse]


class PlaybackEventResponse(BaseModel):
    track: TrackResponse
    played_at: datetime


class PlaybackEventListResponse(PageBase):
    items: list[PlaybackEventResponse]


class TrackStatsResponse(BaseModel):
    track: TrackResponse
    is_liked: bool
    liked_at: datetime | None
    play_count: int
    last_played_at: datetime | None


class TrackUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    artist: str | None = Field(default=None, max_length=512)
    album: str | None = Field(default=None, max_length=512)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Title cannot be null.")
        title = value.strip()
        if not title:
            raise ValueError("Title cannot be blank.")
        return title

    @field_validator("artist", "album")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class PlaylistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _normalize_playlist_name(value)


class PlaylistUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _normalize_playlist_name(value)


class PlaylistTrackAddRequest(BaseModel):
    track_id: UUID


class PlaylistTrackOrderRequest(BaseModel):
    track_ids: list[UUID] = Field(max_length=500)


class PlaylistSummaryResponse(BaseModel):
    id: UUID
    name: str
    track_count: int
    created_at: datetime
    updated_at: datetime


class PlaylistTrackItemResponse(BaseModel):
    position: int
    added_at: datetime
    track: TrackResponse


class PlaylistDetailResponse(BaseModel):
    id: UUID
    name: str
    tracks: list[PlaylistTrackItemResponse]
    created_at: datetime
    updated_at: datetime


class PlaylistListResponse(PageBase):
    items: list[PlaylistSummaryResponse]


def _normalize_playlist_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("Playlist name cannot be blank.")
    return name


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


class CacheStatsResponse(BaseModel):
    total_tracks: int
    total_size_mb: float
    stale_tracks: int
    cache_ttl_days: int
    library_root: str
