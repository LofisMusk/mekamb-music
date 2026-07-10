from __future__ import annotations

from datetime import datetime
from uuid import UUID

from typing import Any

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


class SourceSearchItem(BaseModel):
    source: str
    name: str
    torrent_id: str
    info_hash: str | None = None
    magnet_link: str | None = None
    source_url: str | None = None
    seeders: str
    leechers: str
    size: str | None = None
    size_bytes: int | None = None
    uploader: str


class SourceSearchResponse(BaseModel):
    items: list[SourceSearchItem]


class RecommendationTrackItemResponse(BaseModel):
    track: TrackResponse
    score: float
    reasons: list[str]


class RecommendationSourceCandidateResponse(BaseModel):
    item: SourceSearchItem
    score: float
    query: str
    reasons: list[str]
    already_in_library: bool


class RecommendationResponse(BaseModel):
    seed_track: TrackResponse | None
    local_tracks: list[RecommendationTrackItemResponse]
    external_candidates: list[RecommendationSourceCandidateResponse]


class DailyMixResponse(BaseModel):
    id: str
    title: str
    description: str
    seed_label: str
    tracks: list[RecommendationTrackItemResponse]


class PersonalizedHomeResponse(BaseModel):
    recommended_tracks: list[RecommendationTrackItemResponse]
    daily_mixes: list[DailyMixResponse]


class AutoplayQueueResponse(BaseModel):
    seed_track: TrackResponse
    tracks: list[RecommendationTrackItemResponse]


class RecommendationImportRequest(BaseModel):
    limit: int = Field(default=3, ge=1, le=20)
    sources: list[str] | None = None
    min_seeders: int = Field(default=1, ge=0)


class RecommendationImportItemResponse(BaseModel):
    candidate: RecommendationSourceCandidateResponse
    import_record: ImportRecordResponse | None = None
    error: str | None = None


class RecommendationImportResponse(BaseModel):
    imported: list[RecommendationImportItemResponse]
    skipped: list[RecommendationImportItemResponse]
    failed: list[RecommendationImportItemResponse]


class TrackAudioFeatureResponse(BaseModel):
    track_id: UUID
    tempo: float | None
    energy: float | None
    chroma: float | None
    spectral_centroid: float | None
    mfcc: list[float]
    mood_tags: list[str]
    extractor: str
    features_version: str
    extracted_at: datetime


class IndexerImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    torrent_id: str | None = Field(default=None, max_length=128)
    info_hash: str = Field(min_length=1, max_length=128)
    magnet_link: str = Field(min_length=1)
    uploader: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None, max_length=2048)


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
    completed: bool = True
    listen_ratio: float | None = None


class PlaybackEventRequest(BaseModel):
    completed: bool = True
    listen_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str = Field(default="api", max_length=64)


class PlaybackEventListResponse(PageBase):
    items: list[PlaybackEventResponse]


class PlaybackQueueItemResponse(BaseModel):
    position: int
    added_at: datetime
    track: TrackResponse


class PlaybackStateResponse(BaseModel):
    current_track: TrackResponse | None
    position_seconds: float
    is_playing: bool
    repeat_mode: str
    shuffle: bool
    active_device_id: str | None
    active_device_name: str | None
    queue: list[PlaybackQueueItemResponse]
    updated_at: datetime | None


class PlaybackStateUpdateRequest(BaseModel):
    current_track_id: UUID | None = None
    position_seconds: float = Field(default=0.0, ge=0.0)
    is_playing: bool = False
    repeat_mode: str = Field(default="off", pattern="^(off|track|queue)$")
    shuffle: bool = False
    active_device_id: str | None = Field(default=None, max_length=255)
    active_device_name: str | None = Field(default=None, max_length=255)
    queue_track_ids: list[UUID] = Field(default_factory=list, max_length=500)

    @field_validator("active_device_id", "active_device_name")
    @classmethod
    def normalize_optional_device_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


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


# ── Per-user libraries (curated subsets of the shared catalog) ────────────────
class LibraryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _normalize_library_name(value)


class LibraryUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _normalize_library_name(value)


class LibraryTrackAddRequest(BaseModel):
    track_id: UUID


class LibrarySummaryItemResponse(BaseModel):
    id: UUID
    name: str
    track_count: int
    created_at: datetime
    updated_at: datetime


class LibraryTrackItemResponse(BaseModel):
    position: int
    added_at: datetime
    track: TrackResponse


class LibraryDetailResponse(BaseModel):
    id: UUID
    name: str
    tracks: list[LibraryTrackItemResponse]
    created_at: datetime
    updated_at: datetime


class LibraryListResponse(PageBase):
    items: list[LibrarySummaryItemResponse]


def _normalize_library_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("Library name cannot be blank.")
    return name


# ── Catalog (self-service Lidarr acquisition) ─────────────────────────────────
class CatalogSearchItemResponse(BaseModel):
    kind: str
    foreign_id: str
    title: str
    artist: str | None = None
    artist_foreign_id: str | None = None
    disambiguation: str | None = None
    year: int | None = None


class CatalogSearchResponse(BaseModel):
    items: list[CatalogSearchItemResponse]
    kind: str
    query: str


class CatalogAddRequest(BaseModel):
    kind: str = Field(pattern="^(artist|album)$")
    foreign_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    artist: str | None = Field(default=None, max_length=512)
    artist_foreign_id: str | None = Field(default=None, max_length=128)


class CatalogRequestResponse(BaseModel):
    id: UUID
    kind: str
    foreign_id: str
    title: str
    status: str
    created_at: datetime


class CatalogRequestListResponse(BaseModel):
    items: list[CatalogRequestResponse]


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


class SyncActionResponse(BaseModel):
    id: UUID
    action_type: str
    entity_type: str
    entity_id: str | None
    payload: dict[str, Any]
    origin_instance_id: str
    created_at: datetime
    applied_at: datetime | None
    apply_error: str | None


class SyncActionListResponse(PageBase):
    items: list[SyncActionResponse]
    since: datetime | None
    include_applied: bool


class SyncActionPushItem(BaseModel):
    id: UUID
    action_type: str = Field(min_length=1, max_length=64)
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: str | None = Field(default=None, max_length=255)
    payload: dict[str, Any]
    origin_instance_id: str = Field(min_length=1, max_length=255)
    created_at: datetime


class SyncActionPushRequest(BaseModel):
    items: list[SyncActionPushItem] = Field(max_length=1000)


class SyncActionPushResponse(BaseModel):
    accepted: int
    skipped_existing: int


class SyncApplyResponse(BaseModel):
    applied: int
    failed: int
    items: list[SyncActionResponse]


class SyncImportManifestResponse(BaseModel):
    info_hash: str
    import_record: ImportRecordResponse
    tracks: list[TrackResponse]
