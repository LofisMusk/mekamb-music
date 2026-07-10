package pl.mekamb.music.desktop.data

import java.nio.file.Files
import java.nio.file.Path
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
data class AppSettings(
    val endpoint: String = "",
    // The bearer credential sent on every request: either a legacy API token or,
    // once logged in / migrated, the account session token (same header, either way).
    val apiToken: String = "",
    // Set when apiToken is an account session token; blank for legacy tokens.
    val accountUsername: String = "",
    val accountEmail: String = "",
    val prowlarrApiKey: String = "",
    val autoplaySimilar: Boolean = true,
    val volume: Float = 0.85f,
    val deviceId: String = "",
    val skippedUpdateVersion: String = "",
    val checkUpdatesOnStartup: Boolean = true,
)

/** JSON-file backed settings with atomic writes; in-memory state is authoritative. */
class SettingsStore(
    private val file: Path = AppDirs.configDir.resolve("settings.json"),
) {
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
        prettyPrint = true
    }
    private val writeLock = Any()
    private val _state: MutableStateFlow<AppSettings>
    val state: StateFlow<AppSettings>

    init {
        var loaded = runCatching {
            json.decodeFromString<AppSettings>(Files.readString(file))
        }.getOrElse { AppSettings() }
        if (loaded.deviceId.isBlank()) {
            loaded = loaded.copy(deviceId = UUID.randomUUID().toString())
            persist(loaded)
        }
        _state = MutableStateFlow(loaded)
        state = _state
    }

    fun update(transform: (AppSettings) -> AppSettings) {
        synchronized(writeLock) {
            val next = transform(_state.value)
            if (next == _state.value) return
            _state.value = next
            persist(next)
        }
    }

    private fun persist(settings: AppSettings) {
        // Persistence failures must never crash the app; the flow keeps the live value.
        runCatching {
            Files.createDirectories(file.parent)
            val tmp = file.resolveSibling(file.fileName.toString() + ".tmp")
            Files.writeString(tmp, json.encodeToString(settings))
            atomicReplace(tmp, file)
        }
    }
}
