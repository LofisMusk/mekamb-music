package pl.mekamb.music.desktop.vm

import coil3.ImageLoader
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.http.HttpHeaders
import io.ktor.http.isSuccess
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import pl.mekamb.music.desktop.api.ApiException
import pl.mekamb.music.desktop.api.AuthRegisterResponse
import pl.mekamb.music.desktop.api.AuthUser
import pl.mekamb.music.desktop.api.ClaimTokenRequest
import pl.mekamb.music.desktop.api.LibrarySummary
import pl.mekamb.music.desktop.api.LoginRequest
import pl.mekamb.music.desktop.api.MekambApi
import pl.mekamb.music.desktop.api.PlaylistSummary
import pl.mekamb.music.desktop.api.RegisterRequest
import pl.mekamb.music.desktop.api.Track
import pl.mekamb.music.desktop.api.buildHttpClient
import pl.mekamb.music.desktop.api.normalizeEndpoint
import pl.mekamb.music.desktop.data.DownloadManager
import pl.mekamb.music.desktop.data.SettingsStore
import pl.mekamb.music.desktop.data.buildArtworkImageLoader
import pl.mekamb.music.desktop.player.PlayerController

sealed interface ConnectionState {
    data object Unconfigured : ConnectionState
    data object Connecting : ConnectionState
    data object Connected : ConnectionState
    data class Error(val message: String) : ConnectionState
}

/**
 * Root application container: owns the API client, settings, player, downloads and the
 * observable library snapshot. Instantiated once in [ui.App] and shared through LocalApp.
 */
class AppViewModel {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val httpClient = buildHttpClient()

    val settings = SettingsStore()
    val api = MekambApi(
        client = httpClient,
        baseUrlProvider = { normalizeEndpoint(settings.state.value.endpoint) },
        tokenProvider = { settings.state.value.apiToken },
    )
    val downloads = DownloadManager(api)
    val player = PlayerController(api, downloads, settings)
    val imageLoader: ImageLoader = buildArtworkImageLoader { settings.state.value.apiToken }

    val navigation = MutableStateFlow<Screen>(Screen.Home)

    private val _tracks = MutableStateFlow<List<Track>>(emptyList())
    val tracks: StateFlow<List<Track>> = _tracks

    private val _likedTrackIds = MutableStateFlow<Set<String>>(emptySet())
    val likedTrackIds: StateFlow<Set<String>> = _likedTrackIds

    private val _playlists = MutableStateFlow<List<PlaylistSummary>>(emptyList())
    val playlists: StateFlow<List<PlaylistSummary>> = _playlists

    private val _libraries = MutableStateFlow<List<LibrarySummary>>(emptyList())
    val libraries: StateFlow<List<LibrarySummary>> = _libraries

    private val _connectionState = MutableStateFlow<ConnectionState>(ConnectionState.Unconfigured)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    private val _libraryLoading = MutableStateFlow(false)
    val libraryLoading: StateFlow<Boolean> = _libraryLoading

    init {
        if (isConfigured()) refreshLibrary()
    }

    private fun isConfigured(): Boolean = settings.state.value.let {
        it.endpoint.isNotBlank() && it.apiToken.isNotBlank()
    }

    fun navigate(screen: Screen) {
        navigation.value = screen
    }

    fun refreshLibrary() {
        if (!isConfigured()) {
            _connectionState.value = ConnectionState.Unconfigured
            return
        }
        scope.launch {
            _libraryLoading.value = true
            _connectionState.value = ConnectionState.Connecting
            try {
                val loadedTracks = withContext(Dispatchers.IO) { loadAllTracks() }
                val liked = withContext(Dispatchers.IO) { loadLikedIds() }
                val lists = withContext(Dispatchers.IO) { api.listPlaylists(limit = 200).items }
                val libs = withContext(Dispatchers.IO) { runCatching { api.listLibraries(limit = 200).items }.getOrDefault(emptyList()) }
                _tracks.value = loadedTracks
                _likedTrackIds.value = liked
                _playlists.value = lists
                _libraries.value = libs
                _connectionState.value = ConnectionState.Connected
            } catch (failure: Exception) {
                _connectionState.value = ConnectionState.Error(
                    if (failure is ApiException && failure.isTokenMigrated) {
                        "Your API token was migrated to an account. Log in with your email/username and password in Settings."
                    } else {
                        failure.message ?: "Connection failed"
                    }
                )
            } finally {
                _libraryLoading.value = false
            }
        }
    }

    fun loadLibraries() {
        if (!isConfigured()) return
        scope.launch {
            val libs = withContext(Dispatchers.IO) {
                runCatching { api.listLibraries(limit = 200).items }.getOrDefault(emptyList())
            }
            _libraries.value = libs
        }
    }

    private suspend fun loadAllTracks(): List<Track> {
        val all = mutableListOf<Track>()
        var offset = 0
        val pageSize = 200
        while (all.size < MAX_TRACKS) {
            val page = api.listTracks(limit = pageSize, offset = offset).items
            all += page
            if (page.size < pageSize) break
            offset += pageSize
        }
        return all
    }

    private suspend fun loadLikedIds(): Set<String> {
        val ids = mutableSetOf<String>()
        var offset = 0
        val pageSize = 200
        while (ids.size < MAX_TRACKS) {
            val page = api.likedTracks(limit = pageSize, offset = offset).items
            page.forEach { ids += it.track.id }
            if (page.size < pageSize) break
            offset += pageSize
        }
        return ids
    }

    fun toggleLike(track: Track) {
        val wasLiked = track.id in _likedTrackIds.value
        // Optimistic update, rolled back on failure.
        _likedTrackIds.value = if (wasLiked) _likedTrackIds.value - track.id
        else _likedTrackIds.value + track.id
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                runCatching {
                    if (wasLiked) api.unlikeTrack(track.id) else api.likeTrack(track.id)
                }
            }
            if (result.isFailure) {
                _likedTrackIds.value = if (wasLiked) _likedTrackIds.value + track.id
                else _likedTrackIds.value - track.id
            }
        }
    }

    // ── Accounts ─────────────────────────────────────────────────────────

    private fun deviceName(): String = "Desktop (${System.getProperty("os.name") ?: "unknown"})"

    /** Applies a fresh session: it replaces whatever bearer credential was stored. */
    private fun applySession(token: String, user: AuthUser) {
        settings.update {
            it.copy(apiToken = token, accountUsername = user.username, accountEmail = user.email)
        }
        refreshLibrary()
    }

    suspend fun login(identifier: String, password: String): Result<AuthUser> =
        withContext(Dispatchers.IO) {
            runCatching {
                val session = api.login(LoginRequest(identifier.trim(), password, deviceName()))
                session.user.also { applySession(session.token, it) }
            }
        }

    /** Migrates a legacy API token to an account. On success the server invalidates
     *  the token; the returned session token replaces it locally. */
    suspend fun claimLegacyToken(
        email: String,
        username: String,
        password: String,
        legacyToken: String,
    ): Result<AuthUser> = withContext(Dispatchers.IO) {
        runCatching {
            val session = api.claimToken(
                ClaimTokenRequest(email.trim(), username.trim(), password, legacyToken.trim(), deviceName())
            )
            session.user.also { applySession(session.token, it) }
        }
    }

    suspend fun registerAccount(
        email: String,
        username: String,
        password: String,
    ): Result<AuthRegisterResponse> = withContext(Dispatchers.IO) {
        runCatching {
            val response = api.register(RegisterRequest(email.trim(), username.trim(), password))
            // Approved-on-signup accounts (bootstrap admins) come back with a session.
            response.token?.let { applySession(it, response.user) }
            response
        }
    }

    fun logout() {
        scope.launch {
            withContext(Dispatchers.IO) { runCatching { api.logout() } }
            settings.update { it.copy(apiToken = "", accountUsername = "", accountEmail = "") }
            _tracks.value = emptyList()
            _likedTrackIds.value = emptySet()
            _playlists.value = emptyList()
            _connectionState.value = ConnectionState.Unconfigured
        }
    }

    suspend fun testConnection(endpoint: String, token: String): Result<Unit> =
        withContext(Dispatchers.IO) {
            runCatching {
                val base = normalizeEndpoint(endpoint).trimEnd('/')
                val response = httpClient.get("$base/health") {
                    header(HttpHeaders.Authorization, "Bearer $token")
                }
                if (!response.status.isSuccess()) {
                    throw IllegalStateException("Server returned HTTP ${response.status.value}")
                }
            }
        }

    fun shutdown() {
        runCatching { player.release() }
        scope.cancel()
        runCatching { httpClient.close() }
    }

    private companion object {
        const val MAX_TRACKS = 5000
    }
}
