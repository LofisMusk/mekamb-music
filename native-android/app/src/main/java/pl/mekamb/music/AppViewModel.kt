package pl.mekamb.music

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import pl.mekamb.music.data.AccountInfo
import pl.mekamb.music.data.AdminUser
import pl.mekamb.music.data.Album
import pl.mekamb.music.data.ApiClient
import pl.mekamb.music.data.ApiException
import pl.mekamb.music.data.ApiTrack
import pl.mekamb.music.data.Artist
import pl.mekamb.music.data.CacheStats
import pl.mekamb.music.data.CatalogItem
import pl.mekamb.music.data.CatalogRequestItem
import pl.mekamb.music.data.DailyMix
import pl.mekamb.music.data.ImportRecord
import pl.mekamb.music.data.OfflineStore
import pl.mekamb.music.data.PlaybackBridge
import pl.mekamb.music.data.Playlist
import pl.mekamb.music.data.Prefs
import pl.mekamb.music.data.UserLibrary
import pl.mekamb.music.data.toApiTrack
import java.util.Locale

enum class ConnectionStatus { Unknown, Checking, Connected, Failed }

data class AppUiState(
    val isLoading: Boolean = false,
    val statusMessage: String? = null,
    val isError: Boolean = false,
    val apiEndpoint: String = "",
    /** Bearer token for Coil artwork requests built directly by composables (see ui/nav/AppNav.kt). */
    val apiToken: String = "",
    val accountUsername: String = "",
    val accountEmail: String = "",
    val accountIsAdmin: Boolean = false,
    val tracks: List<ApiTrack> = emptyList(),
    val albums: List<Album> = emptyList(),
    val playlists: List<Playlist> = emptyList(),
    val likedTrackIds: Set<String> = emptySet(),
    val recentPlays: List<ApiTrack> = emptyList(),
    val recommendedTracks: List<ApiTrack> = emptyList(),
    val dailyMixes: List<DailyMix> = emptyList(),
    val libraries: List<UserLibrary> = emptyList(),
    val catalogKind: String = "artist",
    val catalogItems: List<CatalogItem> = emptyList(),
    val catalogRequests: List<CatalogRequestItem> = emptyList(),
    val addedCatalogIds: Set<String> = emptySet(),
    val imports: List<ImportRecord> = emptyList(),
    val activeImportCount: Int = 0,
    val offlineTrackIds: Set<String> = emptySet(),
    val downloadingTrackIds: Set<String> = emptySet(),
    val offlineCount: Int = 0,
    val offlineBytes: Long = 0L,
    val cacheStats: CacheStats? = null,
    val playbackQuality: String = "auto",
    val prefetchQueuedTracks: Boolean = true,
    val downloadOverCellular: Boolean = false,
    val connectionStatus: ConnectionStatus = ConnectionStatus.Unknown,
    val connectionLatencyMs: Long? = null,
) {
    val hasSession: Boolean get() = accountUsername.isNotBlank()
    val canUseApi: Boolean get() = apiEndpoint.isNotBlank() && apiToken.isNotBlank()
    val likedTracks: List<ApiTrack> get() = tracks.filter { likedTrackIds.contains(it.id) }
}

/**
 * Central app ViewModel. Owns the same kind of state `MainActivity` used to hold directly
 * (tracks/albums/playlists/likes/offline state/catalog search/settings), but as a proper
 * ViewModel the Compose screens observe via [uiState] instead of a hand-rolled `render()`. Playback
 * transport itself is untouched — see [PlaybackBridge] and [pl.mekamb.music.Playback].
 */
class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val prefs = Prefs(application)
    private val api = ApiClient(prefs)
    private val offlineStore = OfflineStore(application, prefs)

    val playbackBridge = PlaybackBridge(viewModelScope)
    val playbackState: StateFlow<pl.mekamb.music.data.PlaybackSnapshot> = playbackBridge.state

    private val _uiState = MutableStateFlow(
        AppUiState(
            apiEndpoint = prefs.apiEndpoint,
            apiToken = prefs.apiToken,
            accountUsername = prefs.accountUsername,
            accountEmail = prefs.accountEmail,
            accountIsAdmin = prefs.accountIsAdmin,
            playbackQuality = prefs.playbackQuality,
            prefetchQueuedTracks = prefs.prefetchQueuedTracks,
            downloadOverCellular = prefs.downloadOverCellular,
        ),
    )
    val uiState: StateFlow<AppUiState> = _uiState

    init {
        offlineStore.load()
        refreshOfflineCounts()
        if (prefs.canUseApi()) {
            refreshAccount()
            refreshLibrary()
            loadRecommendations()
            loadLibraries()
            loadCatalogRequests()
            refreshLibrarySummary()
        } else if (offlineStore.trackCount() > 0) {
            _uiState.update { it.copy(statusMessage = "Offline library ready.") }
        }
    }

    override fun onCleared() {
        playbackBridge.dispose()
        super.onCleared()
    }

    private fun setLoading(loading: Boolean) = _uiState.update { it.copy(isLoading = loading) }

    private fun setStatus(message: String?, isError: Boolean = false) =
        _uiState.update { it.copy(statusMessage = message, isError = isError) }

    private fun <T> runIo(showLoading: Boolean = true, task: suspend () -> T, onSuccess: (T) -> Unit) {
        if (showLoading) setLoading(true)
        viewModelScope.launch {
            try {
                val result = withContext(Dispatchers.IO) { task() }
                if (showLoading) setLoading(false)
                onSuccess(result)
            } catch (error: Exception) {
                if (showLoading) setLoading(false)
                setStatus("Error: ${(error as? ApiException)?.message ?: error.message ?: error.javaClass.simpleName}", isError = true)
            }
        }
    }

    // ── Library ──────────────────────────────────────────────────────────────────────────────

    fun refreshLibrary() {
        if (!prefs.canUseApi()) {
            setStatus("Set the API endpoint and log in in Settings.", isError = true)
            return
        }
        runIo(
            task = {
                val tracks = api.loadAllTracks()
                val likes = api.loadAllLikedTrackIds()
                val playlists = api.loadAllPlaylists()
                val recent = runCatching { api.loadRecentPlays() }.getOrDefault(emptyList())
                Quad(tracks, likes, playlists, recent)
            },
            onSuccess = { (tracks, likes, playlists, recent) ->
                val merged = (tracks + playlists.flatMap { it.tracks } + recent)
                    .distinctBy { it.id }
                    .sortedWith(trackComparator())
                val albums = buildAlbums(merged)
                Playback.setLibrary(merged.map { it.toPlaybackTrack() })
                _uiState.update {
                    it.copy(
                        tracks = merged,
                        albums = albums,
                        playlists = playlists.sortedBy { p -> p.name.lowercase(Locale.getDefault()) },
                        likedTrackIds = likes,
                        recentPlays = recent,
                        statusMessage = "Library refreshed: ${merged.size} songs.",
                        isError = false,
                    )
                }
            },
        )
    }

    fun loadRecommendations() {
        if (!prefs.canUseApi()) return
        runIo(
            showLoading = false,
            task = { api.personalizedRecommendations() },
            onSuccess = { (recommended, mixes) ->
                _uiState.update { it.copy(recommendedTracks = recommended, dailyMixes = mixes) }
            },
        )
    }

    fun refreshLibrarySummary() {
        if (!prefs.canUseApi()) return
        runIo(
            showLoading = false,
            task = { api.librarySummary() },
            onSuccess = { summary -> _uiState.update { it.copy(activeImportCount = summary.activeImportCount) } },
        )
    }

    fun toggleLike(track: ApiTrack) {
        val willLike = !_uiState.value.likedTrackIds.contains(track.id)
        _uiState.update {
            it.copy(likedTrackIds = if (willLike) it.likedTrackIds + track.id else it.likedTrackIds - track.id)
        }
        runIo(
            showLoading = false,
            task = { api.setLiked(track.id, willLike) },
            onSuccess = {
                setStatus(if (willLike) "Liked ${track.title}." else "Removed like from ${track.title}.")
            },
        )
    }

    /** Resolves an [Artist] from already-loaded tracks/albums, refetching that artist's tracks
     * from `GET /tracks?artist=` in case the local snapshot is stale or incomplete. */
    fun loadArtist(name: String, onResult: (Artist) -> Unit) {
        val albums = _uiState.value.albums.filter { it.artist == name }
        runIo(
            showLoading = false,
            task = { runCatching { api.loadTracksByArtist(name) }.getOrDefault(emptyList()) },
            onSuccess = { fetched ->
                val byId = _uiState.value.tracks.associateBy { it.id }
                val topTracks = (fetched + albums.flatMap { it.tracks })
                    .distinctBy { it.id }
                    .map { byId[it.id] ?: it }
                    .sortedByDescending { it.createdAt ?: "" }
                    .take(10)
                onResult(Artist(name = name, albums = albums, topTracks = topTracks))
            },
        )
    }

    // ── Playlists / My Libraries ─────────────────────────────────────────────────────────────

    fun createPlaylist(name: String) {
        val trimmed = name.trim()
        if (trimmed.isEmpty() || !prefs.canUseApi()) return
        runIo(
            showLoading = false,
            task = { api.createPlaylist(trimmed) },
            onSuccess = { playlist ->
                _uiState.update { it.copy(playlists = (it.playlists.filterNot { p -> p.id == playlist.id } + playlist).sortedBy { p -> p.name.lowercase(Locale.getDefault()) }) }
                setStatus("Created playlist ${playlist.name}.")
            },
        )
    }

    fun deletePlaylist(playlist: Playlist) {
        runIo(
            showLoading = false,
            task = { api.deletePlaylist(playlist.id) },
            onSuccess = {
                _uiState.update { it.copy(playlists = it.playlists.filterNot { p -> p.id == playlist.id }) }
                setStatus("Deleted playlist ${playlist.name}.")
            },
        )
    }

    fun addTrackToPlaylist(track: ApiTrack, playlist: Playlist) {
        runIo(
            showLoading = false,
            task = { api.addTrackToPlaylist(playlist.id, track.id) },
            onSuccess = { updated ->
                _uiState.update { it.copy(playlists = it.playlists.map { p -> if (p.id == updated.id) updated else p }) }
                setStatus("Added ${track.title} to ${updated.name}.")
            },
        )
    }

    fun loadLibraries() {
        if (!prefs.canUseApi()) return
        runIo(showLoading = false, task = { api.loadLibraries() }, onSuccess = { libs -> _uiState.update { it.copy(libraries = libs) } })
    }

    fun createLibrary(name: String) {
        if (name.isBlank() || !prefs.canUseApi()) return
        runIo(showLoading = false, task = { api.createLibrary(name.trim()) }, onSuccess = { loadLibraries() })
    }

    // ── Catalog (Add Music) ──────────────────────────────────────────────────────────────────

    fun setCatalogKind(kind: String) = _uiState.update { it.copy(catalogKind = kind) }

    fun searchCatalog(query: String) {
        if (!prefs.canUseApi()) {
            setStatus("Set the API endpoint and log in in Settings.", isError = true)
            return
        }
        if (query.isBlank()) {
            _uiState.update { it.copy(catalogItems = emptyList()) }
            return
        }
        runIo(
            task = { api.searchCatalog(_uiState.value.catalogKind, query) },
            onSuccess = { items -> _uiState.update { it.copy(catalogItems = items, statusMessage = "Found ${items.size} catalog results.") } },
        )
    }

    fun addToCatalog(item: CatalogItem) {
        runIo(
            showLoading = false,
            task = { api.addToCatalog(item) },
            onSuccess = { requests ->
                _uiState.update { it.copy(catalogRequests = requests, addedCatalogIds = it.addedCatalogIds + item.id, statusMessage = "Requested: ${item.title}") }
            },
        )
    }

    fun loadCatalogRequests() {
        if (!prefs.canUseApi()) return
        runIo(showLoading = false, task = { api.loadCatalogRequests() }, onSuccess = { requests -> _uiState.update { it.copy(catalogRequests = requests) } })
    }

    // ── Imports ───────────────────────────────────────────────────────────────────────────────

    fun loadImports() {
        if (!prefs.canUseApi()) return
        runIo(showLoading = false, task = { api.loadImports(limit = 100) }, onSuccess = { items -> _uiState.update { it.copy(imports = items) } })
        refreshLibrarySummary()
    }

    fun cancelImport(id: String) {
        runIo(showLoading = false, task = { api.cancelImport(id) }, onSuccess = { loadImports() })
    }

    fun retryImport(id: String) {
        runIo(showLoading = false, task = { api.retryImport(id) }, onSuccess = { loadImports() })
    }

    // ── Playback controls (thin forwards to Playback) ───────────────────────────────────────

    fun playTrack(track: ApiTrack, queue: List<ApiTrack>) {
        if (!offlineStore.isOffline(track.id) && !prefs.canUseApi()) {
            setStatus("Set the API endpoint and log in before streaming.", isError = true)
            return
        }
        val effectiveQueue = queue.ifEmpty { _uiState.value.tracks }
        val playbackQueue = effectiveQueue.map { it.toPlaybackTrack() }
        val index = playbackQueue.indexOfFirst { it.id == track.id }.coerceAtLeast(0)
        Playback.play(playbackQueue, index)
        setStatus(null)
    }

    fun togglePlayback() {
        if (Playback.currentTrack == null) {
            _uiState.value.tracks.firstOrNull()?.let { playTrack(it, _uiState.value.tracks) }
            return
        }
        Playback.toggle()
    }

    fun next() = Playback.next()
    fun previous() = Playback.previous()
    fun toggleShuffle() = Playback.setShuffle(!Playback.shuffle)
    fun cycleRepeat() = Playback.setRepeat(
        when (Playback.repeatMode) {
            RepeatMode.Off -> RepeatMode.All
            RepeatMode.All -> RepeatMode.One
            RepeatMode.One -> RepeatMode.Off
        },
    )
    fun seekTo(ms: Int) = Playback.seekTo(ms)

    /** Jumps to an existing position in the current queue — used by the "Up Next" list in the
     * Now Playing sheet. Reuses [Playback.play] with the same queue rather than adding new queue
     * logic to Playback.kt. */
    fun playQueueIndex(index: Int) {
        val queue = Playback.queue
        if (index in queue.indices) Playback.play(queue, index)
    }

    /** Resolves the currently playing track back to a full library [ApiTrack] when possible. */
    fun currentApiTrack(): ApiTrack? = Playback.currentTrack?.let { pb ->
        _uiState.value.tracks.firstOrNull { it.id == pb.id } ?: pb.toApiTrack()
    }

    // ── Offline downloads ────────────────────────────────────────────────────────────────────

    private fun refreshOfflineCounts() {
        _uiState.update {
            it.copy(
                offlineTrackIds = offlineStore.offlineTrackIds,
                offlineCount = offlineStore.trackCount(),
                offlineBytes = offlineStore.totalBytes(),
            )
        }
    }

    fun downloadTrack(track: ApiTrack) {
        if (offlineStore.isOffline(track.id) || _uiState.value.downloadingTrackIds.contains(track.id)) return
        if (!prefs.canUseApi()) {
            setStatus("Set the API endpoint and log in before downloading.", isError = true)
            return
        }
        if (!offlineStore.canDownloadOnCurrentNetwork()) {
            setStatus("On cellular — enable \"Download over cellular\" in Settings to allow this.", isError = true)
            return
        }
        _uiState.update { it.copy(downloadingTrackIds = it.downloadingTrackIds + track.id) }
        runIo(
            showLoading = false,
            task = { offlineStore.downloadTrack(track) },
            onSuccess = {
                _uiState.update { it.copy(downloadingTrackIds = it.downloadingTrackIds - track.id) }
                refreshOfflineCounts()
                setStatus("${track.title} is available offline.")
            },
        )
    }

    fun removeOfflineTrack(track: ApiTrack) {
        runIo(
            showLoading = false,
            task = { offlineStore.removeTrack(track.id) },
            onSuccess = { refreshOfflineCounts(); setStatus("Removed download for ${track.title}.") },
        )
    }

    fun clearOfflineDownloads() {
        runIo(
            showLoading = false,
            task = { offlineStore.clearAll() },
            onSuccess = { refreshOfflineCounts(); setStatus("Removed offline downloads.") },
        )
    }

    fun isTrackOffline(trackId: String) = offlineStore.isOffline(trackId)

    // ── Settings ──────────────────────────────────────────────────────────────────────────────

    fun setApiEndpoint(value: String) {
        prefs.apiEndpoint = value.trim()
        _uiState.update { it.copy(apiEndpoint = prefs.apiEndpoint, connectionStatus = ConnectionStatus.Unknown) }
    }

    fun testConnection() {
        if (prefs.normalizedEndpoint().isBlank()) {
            setStatus("Enter an API endpoint first.", isError = true)
            return
        }
        _uiState.update { it.copy(connectionStatus = ConnectionStatus.Checking) }
        val started = System.currentTimeMillis()
        runIo(
            showLoading = false,
            task = { api.testConnection() },
            onSuccess = {
                val latency = System.currentTimeMillis() - started
                _uiState.update { it.copy(connectionStatus = ConnectionStatus.Connected, connectionLatencyMs = latency) }
            },
        )
    }

    fun setPlaybackQuality(value: String) {
        prefs.playbackQuality = value
        _uiState.update { it.copy(playbackQuality = value) }
    }

    fun setPrefetchQueuedTracks(value: Boolean) {
        prefs.prefetchQueuedTracks = value
        _uiState.update { it.copy(prefetchQueuedTracks = value) }
    }

    fun setDownloadOverCellular(value: Boolean) {
        prefs.downloadOverCellular = value
        _uiState.update { it.copy(downloadOverCellular = value) }
    }

    fun loadCacheStats() {
        if (!prefs.canUseApi()) return
        runIo(showLoading = false, task = { api.cacheStats() }, onSuccess = { stats -> _uiState.update { it.copy(cacheStats = stats) } })
    }

    fun clearStreamingCache() {
        runIo(showLoading = false, task = { api.cleanupCache() }, onSuccess = { setStatus("Streaming cache cleared."); loadCacheStats() })
    }

    // ── Auth ──────────────────────────────────────────────────────────────────────────────────

    private fun deviceName(): String = "Android (${android.os.Build.MODEL})"

    private fun applySession(token: String, account: AccountInfo) {
        prefs.apiToken = token
        prefs.accountUsername = account.username
        prefs.accountEmail = account.email
        prefs.accountIsAdmin = account.isAdmin
        _uiState.update {
            it.copy(
                apiToken = token,
                accountUsername = account.username,
                accountEmail = account.email,
                accountIsAdmin = account.isAdmin,
            )
        }
    }

    fun login(identifier: String, password: String) {
        if (identifier.isBlank() || password.isBlank()) {
            setStatus("Enter your email/username and password.", isError = true)
            return
        }
        runIo(
            task = { api.login(identifier, password, deviceName()) },
            onSuccess = { (token, account) ->
                applySession(token, account)
                setStatus("Signed in as ${account.username}.")
                refreshLibrary(); loadRecommendations(); loadLibraries(); loadCatalogRequests(); refreshLibrarySummary()
            },
        )
    }

    /** Refreshes account info from /auth/me; keeps admin/status current and, on a revoked/expired
     * session (401), signs out so the app drops back to the login gate. */
    fun refreshAccount() {
        if (!prefs.canUseApi()) return
        runIo(
            showLoading = false,
            task = { api.me() },
            onSuccess = { account ->
                prefs.accountUsername = account.username
                prefs.accountEmail = account.email
                prefs.accountIsAdmin = account.isAdmin
                _uiState.update {
                    it.copy(
                        accountUsername = account.username,
                        accountEmail = account.email,
                        accountIsAdmin = account.isAdmin,
                    )
                }
            },
        )
    }

    fun register(email: String, username: String, password: String) {
        if (email.isBlank() || username.isBlank() || password.isBlank()) {
            setStatus("Fill in the email, username and password.", isError = true)
            return
        }
        runIo(
            task = { api.register(email, username, password) },
            onSuccess = { (session, message) ->
                if (session != null) {
                    val (token, account) = session
                    applySession(token, account)
                    refreshLibrary(); loadRecommendations()
                }
                setStatus(message ?: "Account created.")
            },
        )
    }

    fun logout() {
        runIo(
            task = { runCatching { api.logout() } },
            onSuccess = {
                prefs.clearSession()
                _uiState.update {
                    it.copy(
                        apiToken = "", accountUsername = "", accountEmail = "", accountIsAdmin = false,
                        tracks = emptyList(), albums = emptyList(), playlists = emptyList(),
                        likedTrackIds = emptySet(), dailyMixes = emptyList(), recommendedTracks = emptyList(),
                    )
                }
                setStatus("Logged out.")
            },
        )
    }

    // ── Admin account approval ───────────────────────────────────────────────────────────────────

    /** Loads pending + approved accounts for the admin panel. No-op for non-admins. */
    fun loadAdminUsers(onResult: (pending: List<AdminUser>, approved: List<AdminUser>) -> Unit) {
        if (!_uiState.value.accountIsAdmin) return
        runIo(
            showLoading = false,
            task = { api.adminUsers("pending") to api.adminUsers("approved") },
            onSuccess = { (pending, approved) -> onResult(pending, approved) },
        )
    }

    fun setUserApproval(id: String, approve: Boolean, onDone: () -> Unit) {
        runIo(
            showLoading = false,
            task = { api.setUserApproval(id, approve) },
            onSuccess = {
                setStatus(if (approve) "Account approved." else "Account rejected.")
                onDone()
            },
        )
    }

    // ── Helpers ───────────────────────────────────────────────────────────────────────────────

    /** Data classes auto-generate componentN(), which is all the destructuring in [runIo] above needs. */
    private data class Quad<A, B, C, D>(val a: A, val b: B, val c: C, val d: D)

    private fun trackComparator(): Comparator<ApiTrack> = compareBy(
        { it.displayArtist.lowercase(Locale.getDefault()) },
        { it.displayAlbum.lowercase(Locale.getDefault()) },
        { leadingTrackNumber(it.originalFilename ?: it.title) ?: Int.MAX_VALUE },
        { it.title.lowercase(Locale.getDefault()) },
    )

    private fun leadingTrackNumber(value: String): Int? =
        Regex("""^\D*(\d{1,3})""").find(value)?.groupValues?.getOrNull(1)?.toIntOrNull()

    private fun normalizedAlbumId(album: String): String =
        album.trim().lowercase(Locale.getDefault()).replace(Regex("""\s+"""), " ")

    private fun buildAlbums(sourceTracks: List<ApiTrack>): List<Album> = sourceTracks
        .groupBy { normalizedAlbumId(it.displayAlbum) }
        .map { (id, albumTracks) ->
            val dominant = albumTracks.groupingBy { it.displayArtist }.eachCount().maxByOrNull { it.value }?.key ?: "Unknown Artist"
            Album(id = id, title = albumTracks.first().displayAlbum, artist = dominant, tracks = albumTracks.sortedWith(trackComparator()))
        }
        .sortedWith(compareBy({ it.title.lowercase(Locale.getDefault()) }, { it.artist.lowercase(Locale.getDefault()) }))
}
