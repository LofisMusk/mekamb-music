package pl.mekamb.music.data

import pl.mekamb.music.PlaybackTrack

/** Mirrors the backend's `TrackResponse` (see app/api/routes/tracks.py). */
data class ApiTrack(
    val id: String,
    val title: String,
    val artist: String?,
    val album: String?,
    val originalFilename: String?,
    val mediaType: String?,
    val durationSeconds: Double?,
    val sizeBytes: Long?,
    val createdAt: String?,
) {
    val displayArtist: String get() = artist?.takeIf { it.isNotBlank() } ?: "Unknown Artist"
    val displayAlbum: String get() = album?.takeIf { it.isNotBlank() } ?: "Unknown Album"

    fun toPlaybackTrack(): PlaybackTrack =
        PlaybackTrack(id, title, artist, album, originalFilename, mediaType, durationSeconds)
}

fun PlaybackTrack.toApiTrack(): ApiTrack =
    ApiTrack(id, title, artist, album, originalFilename, mediaType, durationSeconds, null, null)

/** Client-derived grouping of tracks sharing a `displayAlbum` — the backend has no Album entity. */
data class Album(
    val id: String,
    val title: String,
    val artist: String,
    val tracks: List<ApiTrack>,
)

/** Client-derived "artist" — the backend only exposes `artist` as a plain string on tracks. */
data class Artist(
    val name: String,
    val albums: List<Album>,
    val topTracks: List<ApiTrack>,
)

data class Playlist(
    val id: String,
    val name: String,
    val tracks: List<ApiTrack>,
    val updatedAt: String?,
) {
    val trackCountText: String get() = if (tracks.size == 1) "1 song" else "${tracks.size} songs"
}

/** One entry of `GET /recommendations/personalized`'s `daily_mixes[]`. */
data class DailyMix(
    val id: String,
    val title: String,
    val description: String,
    val seedLabel: String?,
    val tracks: List<ApiTrack>,
) {
    val totalMinutes: Int get() = (tracks.sumOf { it.durationSeconds ?: 0.0 } / 60.0).let { Math.round(it).toInt() }
}

data class CatalogItem(
    val kind: String,
    val foreignId: String,
    val title: String,
    val artist: String?,
    val artistForeignId: String?,
    val disambiguation: String?,
    val year: Int?,
) {
    val id: String get() = "$kind:$foreignId"
    val subtitle: String
        get() = listOfNotNull(
            artist?.takeIf { it.isNotBlank() },
            year?.toString(),
            disambiguation?.takeIf { it.isNotBlank() },
        ).joinToString(" · ")
}

data class CatalogRequestItem(
    val id: String,
    val kind: String,
    val foreignId: String,
    val title: String,
    val status: String,
)

/** A personal library ("My Libraries" curated subset), distinct from the Imports concept below. */
data class UserLibrary(
    val id: String,
    val name: String,
    val trackCount: Int,
)

/** Import tracking status enum from the backend (`ImportRecordResponse.status`). */
enum class ImportStatus(val raw: String) {
    Queued("queued"),
    Downloading("downloading"),
    ReadyToImport("ready_to_import"),
    Imported("imported"),
    Failed("failed"),
    Canceled("canceled");

    val isActive: Boolean get() = this == Queued || this == Downloading || this == ReadyToImport

    companion object {
        fun from(raw: String): ImportStatus = entries.firstOrNull { it.raw == raw } ?: Queued
    }
}

/** Mirrors `ImportRecordResponse` from `GET /imports`. */
data class ImportRecord(
    val id: String,
    val source: String?,
    val torrentId: String?,
    val uploader: String?,
    val status: ImportStatus,
    val errorMessage: String?,
    val createdAt: String?,
    val updatedAt: String?,
    val title: String,
)

data class LibrarySummaryInfo(
    val activeImportCount: Int,
    val failedImportCount: Int,
)

/** `GET /tracks/cache/stats` response. */
data class CacheStats(
    val totalTracks: Int,
    val totalSizeMb: Double,
    val staleTracks: Int,
    val cacheTtlDays: Int,
)

data class AccountInfo(
    val username: String,
    val email: String,
    val isAdmin: Boolean = false,
)

/** A user row from the admin approval panel (`GET /admin/users`). */
data class AdminUser(
    val id: String,
    val username: String,
    val email: String,
    val status: String,
    val isAdmin: Boolean,
)
