package pl.mekamb.music.desktop.data

import java.nio.file.Files
import java.nio.file.Path
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import pl.mekamb.music.desktop.api.Track
import pl.mekamb.music.desktop.api.apiJson

@Serializable
data class OfflineTrackRecord(
    val track: Track,
    val relativePath: String,
    val downloadedAt: String,
    val sizeBytes: Long,
)

/**
 * Index of tracks downloaded for offline use. Records whose files disappeared
 * (user deleted them manually, cache wipe, ...) are dropped on load.
 */
class OfflineLibraryStore(
    val directory: Path = AppDirs.dataDir.resolve("Offline"),
) {
    private val indexFile = directory.resolve("offline-library.json")
    private val lock = Any()
    private val _records: MutableStateFlow<List<OfflineTrackRecord>>
    val records: StateFlow<List<OfflineTrackRecord>>

    init {
        Files.createDirectories(directory)
        val loaded = runCatching {
            apiJson.decodeFromString<List<OfflineTrackRecord>>(Files.readString(indexFile))
        }.getOrElse { emptyList() }
        val existing = loaded.filter { Files.exists(directory.resolve(it.relativePath)) }
        _records = MutableStateFlow(existing)
        records = _records
        if (existing.size != loaded.size) persist(existing)
    }

    fun list(): List<OfflineTrackRecord> = _records.value

    fun get(trackId: String): OfflineTrackRecord? =
        _records.value.firstOrNull { it.track.id == trackId }

    fun pathFor(trackId: String): Path? = get(trackId)
        ?.let { directory.resolve(it.relativePath) }
        ?.takeIf { Files.exists(it) }

    fun add(record: OfflineTrackRecord) {
        synchronized(lock) {
            val next = _records.value.filterNot { it.track.id == record.track.id } + record
            _records.value = next
            persist(next)
        }
    }

    fun remove(trackId: String): OfflineTrackRecord? {
        synchronized(lock) {
            val record = _records.value.firstOrNull { it.track.id == trackId } ?: return null
            val next = _records.value.filterNot { it.track.id == trackId }
            _records.value = next
            persist(next)
            return record
        }
    }

    private fun persist(records: List<OfflineTrackRecord>) {
        runCatching {
            Files.createDirectories(directory)
            val tmp = indexFile.resolveSibling(indexFile.fileName.toString() + ".tmp")
            Files.writeString(tmp, apiJson.encodeToString(records))
            atomicReplace(tmp, indexFile)
        }
    }
}
