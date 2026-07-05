package pl.mekamb.music.desktop.data

import io.ktor.client.statement.bodyAsChannel
import io.ktor.http.isSuccess
import io.ktor.utils.io.readAvailable
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.time.Instant
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import pl.mekamb.music.desktop.api.MekambApi
import pl.mekamb.music.desktop.api.Track

/**
 * Manages offline downloads (persisted permanently) and the transient playback prefetch cache.
 * All network work happens on an IO scope; UI observes progress via StateFlows.
 */
class DownloadManager(
    private val api: MekambApi,
    private val offlineStore: OfflineLibraryStore = OfflineLibraryStore(),
    private val cacheDir: Path = AppDirs.cacheDir.resolve("playback"),
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val cacheLock = Mutex()

    private val _activeDownloads = MutableStateFlow<Map<String, Float>>(emptyMap())
    val activeDownloads: StateFlow<Map<String, Float>> = _activeDownloads

    val offlineTrackIds: StateFlow<Set<String>> by lazy {
        // Mirror the offline store's records as a simple id set.
        val flow = MutableStateFlow(offlineStore.list().map { it.track.id }.toSet())
        scope.launch {
            offlineStore.records.collect { records ->
                flow.value = records.map { it.track.id }.toSet()
            }
        }
        flow
    }

    init {
        Files.createDirectories(cacheDir)
    }

    fun offlinePath(trackId: String): Path? = offlineStore.pathFor(trackId)

    fun cachedPath(trackId: String): Path? =
        findCacheFile(trackId)?.takeIf { Files.exists(it) }

    fun downloadTrack(track: Track) {
        if (offlineStore.get(track.id) != null) return
        if (_activeDownloads.value.containsKey(track.id)) return
        scope.launch { downloadToOffline(track) }
    }

    fun downloadTracks(tracks: List<Track>) {
        tracks.forEach { downloadTrack(it) }
    }

    fun removeDownload(trackId: String) {
        val record = offlineStore.remove(trackId) ?: return
        runCatching { Files.deleteIfExists(offlineStore.directory.resolve(record.relativePath)) }
    }

    fun removeAllDownloads() {
        offlineStore.list().forEach { removeDownload(it.track.id) }
    }

    fun storageUsageBytes(): Long =
        offlineStore.list().sumOf { it.sizeBytes.coerceAtLeast(0) }

    /** Fire-and-forget prefetch of a track into the LRU playback cache (offline tracks are skipped). */
    fun prefetchToCache(track: Track) {
        if (offlinePath(track.id) != null || cachedPath(track.id) != null) return
        scope.launch {
            cacheLock.withLock {
                if (cachedPath(track.id) != null) return@withLock
                runCatching {
                    val target = cacheDir.resolve("${track.id}.${extensionFor(track)}")
                    streamTo(api.streamUrl(track.id), target, onProgress = null)
                    pruneCache()
                }
            }
        }
    }

    private suspend fun downloadToOffline(track: Track) {
        _activeDownloads.update { it + (track.id to 0f) }
        try {
            val fileName = "${track.id}.${extensionFor(track)}"
            val target = offlineStore.directory.resolve(fileName)
            Files.createDirectories(offlineStore.directory)
            val size = streamTo(api.streamUrl(track.id), target) { progress ->
                _activeDownloads.update { it + (track.id to progress) }
            }
            offlineStore.add(
                OfflineTrackRecord(
                    track = track,
                    relativePath = fileName,
                    downloadedAt = Instant.now().toString(),
                    sizeBytes = size,
                ),
            )
        } catch (failure: Exception) {
            // Leave no partial file behind on failure.
            runCatching {
                Files.deleteIfExists(offlineStore.directory.resolve("${track.id}.${extensionFor(track)}"))
            }
        } finally {
            _activeDownloads.update { it - track.id }
        }
    }

    private suspend fun streamTo(url: String, target: Path, onProgress: ((Float) -> Unit)?): Long {
        val response = api.rawGet(url)
        if (!response.status.isSuccess()) {
            throw IllegalStateException("Download failed: HTTP ${response.status.value}")
        }
        val total = response.headers["Content-Length"]?.toLongOrNull()
        val temp = Files.createTempFile(target.parent, target.fileName.toString(), ".part")
        var written = 0L
        try {
            val channel = response.bodyAsChannel()
            Files.newOutputStream(temp).use { out ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    val read = channel.readAvailable(buffer, 0, buffer.size)
                    if (read == -1) break
                    if (read > 0) {
                        out.write(buffer, 0, read)
                        written += read
                        if (total != null && total > 0) {
                            onProgress?.invoke((written.toDouble() / total).toFloat().coerceIn(0f, 1f))
                        }
                    }
                }
            }
            try {
                Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
            } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
                Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING)
            }
            onProgress?.invoke(1f)
            return written
        } finally {
            Files.deleteIfExists(temp)
        }
    }

    private fun findCacheFile(trackId: String): Path? {
        if (!Files.isDirectory(cacheDir)) return null
        return runCatching {
            Files.list(cacheDir).use { stream ->
                stream.filter { it.fileName.toString().substringBeforeLast('.') == trackId }
                    .findFirst()
                    .orElse(null)
            }
        }.getOrNull()
    }

    /** Keeps the playback cache bounded to the most-recently-modified files. */
    private fun pruneCache(maxFiles: Int = 10) {
        runCatching {
            Files.list(cacheDir).use { stream ->
                val files = stream.toList().filter { Files.isRegularFile(it) }
                if (files.size <= maxFiles) return
                files.sortedByDescending { Files.getLastModifiedTime(it).toMillis() }
                    .drop(maxFiles)
                    .forEach { runCatching { Files.deleteIfExists(it) } }
            }
        }
    }

    private fun extensionFor(track: Track): String {
        track.originalFilename?.substringAfterLast('.', "")?.takeIf { it.isNotBlank() && it.length <= 5 }
            ?.let { return it.lowercase() }
        return when (track.mediaType?.lowercase()) {
            "audio/mpeg", "audio/mp3" -> "mp3"
            "audio/flac", "audio/x-flac" -> "flac"
            "audio/mp4", "audio/aac", "audio/x-m4a" -> "m4a"
            "audio/ogg", "audio/opus" -> "ogg"
            "audio/wav", "audio/x-wav" -> "wav"
            else -> "audio"
        }
    }
}
