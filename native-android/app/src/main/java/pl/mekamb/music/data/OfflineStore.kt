package pl.mekamb.music.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

private data class OfflineRecord(
    val track: ApiTrack,
    val relativePath: String,
    val sizeBytes: Long,
    val downloadedAt: Long,
)

/**
 * Offline-download bookkeeping, ported from `MainActivity`'s `offlineRecords`/`OfflineRecord`
 * logic. Downloads land in the same `filesDir/offline/tracks` directory [pl.mekamb.music.Playback]
 * already checks first when resolving a playable file, so a track downloaded here plays back
 * without hitting the network even though this class doesn't touch Playback.kt.
 */
class OfflineStore(private val context: Context, private val prefs: Prefs) {
    private val offlineTrackDir = File(context.filesDir, "offline/tracks").apply { mkdirs() }
    private var records: MutableMap<String, OfflineRecord> = mutableMapOf()

    val offlineTrackIds: Set<String> get() = records.keys

    fun trackCount(): Int = records.size

    fun totalBytes(): Long = records.values.sumOf { record ->
        offlineFile(record.relativePath).let { if (it.isFile) it.length() else 0L }
    }

    fun isOffline(trackId: String): Boolean = records.containsKey(trackId)

    fun load() {
        val items = runCatching { JSONArray(prefs.offlineRecordsJson) }.getOrNull() ?: JSONArray()
        val loaded = mutableMapOf<String, OfflineRecord>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            val trackJson = item.optJSONObject("track") ?: continue
            val track = parseOfflineTrack(trackJson) ?: continue
            val relativePath = item.optCleanString("relative_path") ?: continue
            val file = offlineFile(relativePath)
            if (!file.isFile || file.length() <= 0L) continue
            loaded[track.id] = OfflineRecord(
                track = track,
                relativePath = relativePath,
                sizeBytes = item.optNullableLong("size_bytes") ?: file.length(),
                downloadedAt = item.optNullableLong("downloaded_at") ?: 0L,
            )
        }
        records = loaded
    }

    private fun save() {
        val items = JSONArray()
        records.values.sortedByDescending { it.downloadedAt }.forEach { record ->
            items.put(
                JSONObject()
                    .put("track", trackJson(record.track))
                    .put("relative_path", record.relativePath)
                    .put("size_bytes", record.sizeBytes)
                    .put("downloaded_at", record.downloadedAt),
            )
        }
        prefs.saveOfflineRecordsJson(items.toString())
    }

    /** True when a cellular download is safe to start given [Prefs.downloadOverCellular]. */
    fun canDownloadOnCurrentNetwork(): Boolean {
        if (prefs.downloadOverCellular) return true
        val manager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? android.net.ConnectivityManager
            ?: return true
        return !manager.isActiveNetworkMetered
    }

    suspend fun downloadTrack(track: ApiTrack) {
        if (records.containsKey(track.id)) return
        withContext(Dispatchers.IO) {
            val file = offlineFileFor(track)
            downloadToFile(track, file)
            records[track.id] = OfflineRecord(track, file.name, file.length(), System.currentTimeMillis())
            save()
        }
    }

    suspend fun removeTrack(trackId: String) {
        withContext(Dispatchers.IO) {
            val record = records.remove(trackId) ?: return@withContext
            offlineFile(record.relativePath).delete()
            save()
        }
    }

    suspend fun clearAll() {
        withContext(Dispatchers.IO) {
            records.values.forEach { offlineFile(it.relativePath).delete() }
            records.clear()
            save()
        }
    }

    private fun downloadToFile(track: ApiTrack, output: File) {
        val endpoint = "${prefs.normalizedEndpoint()}/tracks/${android.net.Uri.encode(track.id)}/stream"
        output.parentFile?.mkdirs()
        val temp = File(output.parentFile, "${output.name}.tmp")
        val connection = URL(endpoint).openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.connectTimeout = 20_000
        connection.readTimeout = 90_000
        connection.setRequestProperty("Accept", track.mediaType ?: "audio/*")
        connection.setRequestProperty("Authorization", "Bearer ${prefs.apiToken}")
        val status = connection.responseCode
        if (status !in 200..299) {
            connection.disconnect()
            temp.delete()
            throw ApiException("stream error $status")
        }
        connection.inputStream.use { input -> temp.outputStream().use { input.copyTo(it) } }
        connection.disconnect()
        if (temp.length() <= 0L) {
            temp.delete()
            throw ApiException("empty audio file")
        }
        if (!temp.renameTo(output)) {
            output.delete()
            if (!temp.renameTo(output)) {
                temp.delete()
                throw ApiException("could not save audio file")
            }
        }
    }

    private fun offlineFileFor(track: ApiTrack): File =
        offlineFile("${safeTrackIdentity(track.id)}.${playbackExtension(track)}")

    private fun offlineFile(relativePath: String): File {
        val clean = relativePath.substringAfterLast('/').substringAfterLast('\\')
        return File(offlineTrackDir, clean)
    }

    private fun safeTrackIdentity(trackId: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(trackId.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }

    private fun playbackExtension(track: ApiTrack): String {
        val filenameExtension = track.originalFilename
            ?.substringAfterLast('.', "")
            ?.lowercase()
            ?.filter { it.isLetterOrDigit() }
            ?.takeIf { it.length in 2..5 }
        if (filenameExtension != null) return filenameExtension
        return when (track.mediaType?.lowercase()) {
            "audio/mpeg" -> "mp3"
            "audio/mp4", "audio/aac", "audio/x-m4a" -> "m4a"
            "audio/flac", "audio/x-flac" -> "flac"
            "audio/ogg" -> "ogg"
            "audio/wav", "audio/x-wav" -> "wav"
            else -> "audio"
        }
    }

    private fun trackJson(track: ApiTrack): JSONObject = JSONObject()
        .put("id", track.id)
        .put("title", track.title)
        .put("artist", track.artist)
        .put("album", track.album)
        .put("original_filename", track.originalFilename)
        .put("media_type", track.mediaType)
        .put("duration_seconds", track.durationSeconds)
        .put("size_bytes", track.sizeBytes)
        .put("created_at", track.createdAt)

    private fun parseOfflineTrack(item: JSONObject): ApiTrack? {
        val id = item.optCleanString("id") ?: return null
        return ApiTrack(
            id = id,
            title = item.optCleanString("title") ?: "Untitled",
            artist = item.optCleanString("artist"),
            album = item.optCleanString("album"),
            originalFilename = item.optCleanString("original_filename"),
            mediaType = item.optCleanString("media_type"),
            durationSeconds = item.optNullableDouble("duration_seconds"),
            sizeBytes = item.optNullableLong("size_bytes"),
            createdAt = item.optCleanString("created_at"),
        )
    }
}
