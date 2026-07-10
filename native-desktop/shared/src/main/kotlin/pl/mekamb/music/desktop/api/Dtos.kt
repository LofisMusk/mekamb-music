package pl.mekamb.music.desktop.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

// ── Tracks ──────────────────────────────────────────────────────────────────

@Serializable
data class Track(
    val id: String,
    val title: String,
    val artist: String? = null,
    val album: String? = null,
    @SerialName("storage_key") val storageKey: String? = null,
    @SerialName("original_filename") val originalFilename: String? = null,
    @SerialName("media_type") val mediaType: String? = null,
    val codec: String? = null,
    @SerialName("duration_seconds") val durationSeconds: Double? = null,
    @SerialName("size_bytes") val sizeBytes: Long? = null,
    @SerialName("cover_key") val coverKey: String? = null,
    @SerialName("source_import_id") val sourceImportId: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("last_accessed") val lastAccessed: String? = null,
)

@Serializable
data class TrackListResponse(
    val items: List<Track> = emptyList(),
    val limit: Int = 0,
    val offset: Int = 0,
)

@Serializable
data class LikedTrackItem(
    val track: Track,
    @SerialName("liked_at") val likedAt: String? = null,
)

@Serializable
data class LikedTrackListResponse(
    val items: List<LikedTrackItem> = emptyList(),
    val limit: Int = 0,
    val offset: Int = 0,
)

@Serializable
data class PlaybackEventItem(
    val track: Track,
    @SerialName("played_at") val playedAt: String? = null,
    val completed: Boolean = true,
    @SerialName("listen_ratio") val listenRatio: Double? = null,
)

@Serializable
data class PlaybackEventListResponse(
    val items: List<PlaybackEventItem> = emptyList(),
    val limit: Int = 0,
    val offset: Int = 0,
)

@Serializable
data class PlaybackEventRequest(
    val completed: Boolean = true,
    @SerialName("listen_ratio") val listenRatio: Double? = null,
    val source: String = "desktop",
)

@Serializable
data class TrackStatsResponse(
    val track: Track,
    @SerialName("is_liked") val isLiked: Boolean = false,
    @SerialName("liked_at") val likedAt: String? = null,
    @SerialName("play_count") val playCount: Int = 0,
    @SerialName("last_played_at") val lastPlayedAt: String? = null,
)

@Serializable
data class TrackUpdateRequest(
    val title: String? = null,
    val artist: String? = null,
    val album: String? = null,
)

@Serializable
data class ArtistEntry(
    val name: String,
    @SerialName("track_count") val trackCount: Int = 0,
    @SerialName("latest_track_at") val latestTrackAt: String? = null,
)

@Serializable
data class ArtistListResponse(
    val items: List<ArtistEntry> = emptyList(),
    val limit: Int = 0,
    val offset: Int = 0,
)

@Serializable
data class AlbumEntry(
    val title: String,
    val artist: String? = null,
    @SerialName("track_count") val trackCount: Int = 0,
    @SerialName("latest_track_at") val latestTrackAt: String? = null,
)

@Serializable
data class AlbumListResponse(
    val items: List<AlbumEntry> = emptyList(),
    val limit: Int = 0,
    val offset: Int = 0,
)

// ── Playback state ──────────────────────────────────────────────────────────

@Serializable
data class PlaybackStateUpdateRequest(
    @SerialName("current_track_id") val currentTrackId: String? = null,
    @SerialName("position_seconds") val positionSeconds: Double = 0.0,
    @SerialName("is_playing") val isPlaying: Boolean = false,
    @SerialName("repeat_mode") val repeatMode: String = "off",
    val shuffle: Boolean = false,
    @SerialName("active_device_id") val activeDeviceId: String? = null,
    @SerialName("active_device_name") val activeDeviceName: String? = null,
    @SerialName("queue_track_ids") val queueTrackIds: List<String> = emptyList(),
)

@Serializable
data class PlaybackQueueItem(
    val position: Int,
    @SerialName("added_at") val addedAt: String? = null,
    val track: Track,
)

@Serializable
data class PlaybackStateResponse(
    @SerialName("current_track") val currentTrack: Track? = null,
    @SerialName("position_seconds") val positionSeconds: Double = 0.0,
    @SerialName("is_playing") val isPlaying: Boolean = false,
    @SerialName("repeat_mode") val repeatMode: String = "off",
    val shuffle: Boolean = false,
    @SerialName("active_device_id") val activeDeviceId: String? = null,
    @SerialName("active_device_name") val activeDeviceName: String? = null,
    val queue: List<PlaybackQueueItem> = emptyList(),
    @SerialName("updated_at") val updatedAt: String? = null,
)

// ── Playlists ───────────────────────────────────────────────────────────────

@Serializable
data class PlaylistSummary(
    val id: String,
    val name: String,
    @SerialName("track_count") val trackCount: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class PlaylistListResponse(
    val items: List<PlaylistSummary> = emptyList(),
    val limit: Int = 0,
    val offset: Int = 0,
)

@Serializable
data class PlaylistTrackItem(
    val position: Int,
    @SerialName("added_at") val addedAt: String? = null,
    val track: Track,
)

@Serializable
data class PlaylistDetail(
    val id: String,
    val name: String,
    val tracks: List<PlaylistTrackItem> = emptyList(),
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class PlaylistCreateRequest(val name: String)

@Serializable
data class PlaylistUpdateRequest(val name: String)

@Serializable
data class PlaylistTrackAddRequest(@SerialName("track_id") val trackId: String)

@Serializable
data class PlaylistTrackOrderRequest(@SerialName("track_ids") val trackIds: List<String>)

// ── Sources (torrent / indexer search) ──────────────────────────────────────

@Serializable
data class SourceSearchItem(
    val source: String,
    val name: String,
    @SerialName("torrent_id") val torrentId: String? = null,
    @SerialName("info_hash") val infoHash: String? = null,
    @SerialName("magnet_link") val magnetLink: String? = null,
    @SerialName("source_url") val sourceUrl: String? = null,
    val seeders: String? = null,
    val leechers: String? = null,
    val size: String? = null,
    @SerialName("size_bytes") val sizeBytes: Long? = null,
    val uploader: String? = null,
)

@Serializable
data class SourceSearchResponse(
    val items: List<SourceSearchItem> = emptyList(),
)

// ── Imports & downloads ─────────────────────────────────────────────────────

@Serializable
data class ImportRecord(
    val id: String,
    val source: String? = null,
    @SerialName("torrent_id") val torrentId: String? = null,
    @SerialName("info_hash") val infoHash: String? = null,
    val uploader: String? = null,
    @SerialName("source_url") val sourceUrl: String? = null,
    val status: String,
    @SerialName("quarantine_path") val quarantinePath: String? = null,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class ImportListResponse(
    val items: List<ImportRecord> = emptyList(),
    val limit: Int = 0,
    val offset: Int = 0,
)

@Serializable
data class IndexerImportRequest(
    val name: String,
    @SerialName("torrent_id") val torrentId: String? = null,
    @SerialName("info_hash") val infoHash: String,
    @SerialName("magnet_link") val magnetLink: String,
    val uploader: String? = null,
    @SerialName("source_url") val sourceUrl: String? = null,
)

@Serializable
data class TorrentRuntimeStatus(
    val name: String? = null,
    @SerialName("info_hash") val infoHash: String? = null,
    val state: String? = null,
    val progress: Double? = null,
    @SerialName("size_bytes") val sizeBytes: Long? = null,
    @SerialName("downloaded_bytes") val downloadedBytes: Long? = null,
    @SerialName("download_speed_bytes") val downloadSpeedBytes: Long? = null,
    @SerialName("eta_seconds") val etaSeconds: Long? = null,
    @SerialName("save_path") val savePath: String? = null,
)

@Serializable
data class DownloadStatusResponse(
    @SerialName("import") val importRecord: ImportRecord,
    val torrent: TorrentRuntimeStatus? = null,
)

// ── Recommendations ─────────────────────────────────────────────────────────

@Serializable
data class RecommendationTrackItem(
    val track: Track,
    val score: Double = 0.0,
    val reasons: List<String> = emptyList(),
)

@Serializable
data class RecommendationSourceCandidate(
    val item: SourceSearchItem,
    val score: Double = 0.0,
    val query: String? = null,
    val reasons: List<String> = emptyList(),
    @SerialName("already_in_library") val alreadyInLibrary: Boolean = false,
)

@Serializable
data class RecommendationResponse(
    @SerialName("seed_track") val seedTrack: Track? = null,
    @SerialName("local_tracks") val localTracks: List<RecommendationTrackItem> = emptyList(),
    @SerialName("external_candidates") val externalCandidates: List<RecommendationSourceCandidate> = emptyList(),
)

@Serializable
data class DailyMix(
    val id: String,
    val title: String,
    val description: String? = null,
    @SerialName("seed_label") val seedLabel: String? = null,
    val tracks: List<RecommendationTrackItem> = emptyList(),
)

@Serializable
data class PersonalizedHomeResponse(
    @SerialName("recommended_tracks") val recommendedTracks: List<RecommendationTrackItem> = emptyList(),
    @SerialName("daily_mixes") val dailyMixes: List<DailyMix> = emptyList(),
)

// ── Sync ────────────────────────────────────────────────────────────────────

@Serializable
data class SyncAction(
    val id: String,
    @SerialName("action_type") val actionType: String,
    @SerialName("entity_type") val entityType: String,
    @SerialName("entity_id") val entityId: String? = null,
    val payload: JsonObject? = null,
    @SerialName("origin_instance_id") val originInstanceId: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("applied_at") val appliedAt: String? = null,
    @SerialName("apply_error") val applyError: String? = null,
)

@Serializable
data class SyncActionListResponse(
    val items: List<SyncAction> = emptyList(),
)

// ── Library summary / misc ──────────────────────────────────────────────────

@Serializable
data class LibrarySummaryResponse(
    @SerialName("track_count") val trackCount: Long = 0,
    @SerialName("artist_count") val artistCount: Long = 0,
    @SerialName("album_count") val albumCount: Long = 0,
    @SerialName("playlist_count") val playlistCount: Long = 0,
    @SerialName("liked_track_count") val likedTrackCount: Long = 0,
    @SerialName("playback_event_count") val playbackEventCount: Long = 0,
    @SerialName("import_count") val importCount: Long = 0,
    @SerialName("active_import_count") val activeImportCount: Long = 0,
    @SerialName("failed_import_count") val failedImportCount: Long = 0,
    @SerialName("library_size_bytes") val librarySizeBytes: Long = 0,
    @SerialName("total_duration_seconds") val totalDurationSeconds: Double = 0.0,
    @SerialName("latest_track_at") val latestTrackAt: String? = null,
    @SerialName("latest_import_at") val latestImportAt: String? = null,
)

@Serializable
data class HealthResponse(val status: String)

@Serializable
data class CacheStatsResponse(
    @SerialName("total_tracks") val totalTracks: Long = 0,
    @SerialName("total_size_mb") val totalSizeMb: Double = 0.0,
    @SerialName("stale_tracks") val staleTracks: Long = 0,
    @SerialName("cache_ttl_days") val cacheTtlDays: Int = 0,
    @SerialName("library_root") val libraryRoot: String? = null,
)

// ── Auth (accounts, sessions, token migration) ──────────────────────────────

@Serializable
data class AuthUser(
    val id: String,
    val email: String,
    val username: String,
    val status: String,
    @SerialName("is_admin") val isAdmin: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("approved_at") val approvedAt: String? = null,
)

@Serializable
data class AuthSessionResponse(
    val token: String,
    @SerialName("token_type") val tokenType: String = "bearer",
    val user: AuthUser,
)

@Serializable
data class AuthRegisterResponse(
    val user: AuthUser,
    val token: String? = null,
    @SerialName("token_type") val tokenType: String = "bearer",
    val message: String = "",
)

@Serializable
data class LoginRequest(
    val identifier: String,
    val password: String,
    @SerialName("device_name") val deviceName: String? = null,
)

@Serializable
data class ClaimTokenRequest(
    val email: String,
    val username: String,
    val password: String,
    val token: String,
    @SerialName("device_name") val deviceName: String? = null,
)

@Serializable
data class RegisterRequest(
    val email: String,
    val username: String,
    val password: String,
)

// ── GitHub releases (auto-updater) ──────────────────────────────────────────

@Serializable
data class GhAsset(
    val name: String,
    @SerialName("browser_download_url") val browserDownloadUrl: String,
    val size: Long = 0,
)

@Serializable
data class GhRelease(
    @SerialName("tag_name") val tagName: String,
    val name: String? = null,
    val body: String? = null,
    val draft: Boolean = false,
    val prerelease: Boolean = false,
    @SerialName("published_at") val publishedAt: String? = null,
    val assets: List<GhAsset> = emptyList(),
)
