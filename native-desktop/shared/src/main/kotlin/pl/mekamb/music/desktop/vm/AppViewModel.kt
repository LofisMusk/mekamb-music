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
import pl.mekamb.music.desktop.api.MekambApi
import pl.mekamb.music.desktop.api.PlaylistSummary
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
                _tracks.value = loadedTracks
                _likedTrackIds.value = liked
                _playlists.value = lists
                _connectionState.value = ConnectionState.Connected
            } catch (failure: Exception) {
                _connectionState.value = ConnectionState.Error(failure.message ?: "Connection failed")
            } finally {
                _libraryLoading.value = false
            }
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
