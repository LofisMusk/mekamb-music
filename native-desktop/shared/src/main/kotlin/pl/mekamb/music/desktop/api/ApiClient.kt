package pl.mekamb.music.desktop.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.head
import io.ktor.client.request.header
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import io.ktor.http.encodeURLParameter
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject

class ApiException(
    val statusCode: Int,
    message: String,
    /** Stable machine code from the backend's `detail.code` (e.g. `token_migrated`), if any. */
    val errorCode: String? = null,
    /** Human-readable `detail.message` from the backend, safe to show in UI. */
    val errorMessage: String? = null,
) : Exception(message) {
    val isTokenMigrated: Boolean get() = errorCode == "token_migrated"
    fun userMessage(): String = errorMessage ?: (message ?: "Request failed (HTTP $statusCode)")
}

/** Builds an [ApiException], pulling `detail.code`/`detail.message` out of FastAPI error bodies. */
internal fun apiException(statusCode: Int, body: String): ApiException {
    var code: String? = null
    var msg: String? = null
    runCatching {
        when (val detail = apiJson.parseToJsonElement(body).jsonObject["detail"]) {
            is JsonPrimitive -> msg = detail.content
            is JsonObject -> {
                code = (detail["code"] as? JsonPrimitive)?.content
                msg = (detail["message"] as? JsonPrimitive)?.content
            }
            else -> {}
        }
    }
    return ApiException(statusCode, "HTTP $statusCode: ${msg ?: body.take(300)}", code, msg)
}

/**
 * Normalizes a user-entered endpoint the same way the mobile apps do:
 * trims whitespace, strips trailing slashes, defaults to http:// when no scheme given.
 */
fun normalizeEndpoint(raw: String): String {
    val trimmed = raw.trim().trimEnd('/')
    if (trimmed.isEmpty()) return ""
    return if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) trimmed
    else "http://$trimmed"
}

val apiJson: Json = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    encodeDefaults = true
}

fun buildHttpClient(): HttpClient = HttpClient(CIO) {
    install(ContentNegotiation) { json(apiJson) }
    install(HttpTimeout) {
        connectTimeoutMillis = 15_000
        requestTimeoutMillis = 60_000
        socketTimeoutMillis = 60_000
    }
    expectSuccess = false
}

/**
 * Complete client for the Mekamb Music backend API. Covers every backend endpoint;
 * the `baseUrl` and `token` are read lazily so settings changes apply immediately.
 */
class MekambApi(
    private val client: HttpClient,
    private val baseUrlProvider: () -> String,
    private val tokenProvider: () -> String,
) {
    private fun url(path: String): String = baseUrlProvider().trimEnd('/') + path

    private fun HttpRequestBuilder.auth() {
        header(HttpHeaders.Authorization, "Bearer ${tokenProvider()}")
    }

    private suspend inline fun <reified T> HttpResponse.expect(): T {
        if (!status.isSuccess()) {
            val detail = runCatching { bodyAsText() }.getOrDefault("")
            throw apiException(status.value, detail)
        }
        return body()
    }

    private suspend fun HttpResponse.expectOk() {
        if (!status.isSuccess()) {
            val detail = runCatching { bodyAsText() }.getOrDefault("")
            throw apiException(status.value, detail)
        }
    }

    fun streamUrl(trackId: String): String = url("/tracks/$trackId/stream")
    fun artworkUrl(trackId: String): String = url("/tracks/$trackId/artwork")
    fun currentToken(): String = tokenProvider()

    // ── Health ──────────────────────────────────────────────────────────

    suspend fun health(): HealthResponse = client.get(url("/health")).expect()

    // ── Auth (accounts) ──────────────────────────────────────────────────
    // login/claimToken/register are the front door: no auth header.

    suspend fun login(request: LoginRequest): AuthSessionResponse =
        client.post(url("/auth/login")) {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expect()

    /** Migrates a legacy API token to an account; the token stops working afterwards. */
    suspend fun claimToken(request: ClaimTokenRequest): AuthSessionResponse =
        client.post(url("/auth/claim-token")) {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expect()

    suspend fun register(request: RegisterRequest): AuthRegisterResponse =
        client.post(url("/auth/register")) {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expect()

    suspend fun me(): AuthUser = client.get(url("/auth/me")) { auth() }.expect()

    suspend fun logout() = client.post(url("/auth/logout")) { auth() }.expectOk()

    // ── Tracks ──────────────────────────────────────────────────────────

    suspend fun listTracks(
        query: String? = null,
        artist: String? = null,
        album: String? = null,
        limit: Int = 200,
        offset: Int = 0,
    ): TrackListResponse = client.get(url("/tracks")) {
        auth()
        parameter("limit", limit)
        parameter("offset", offset)
        query?.takeIf { it.isNotBlank() }?.let { parameter("q", it) }
        artist?.takeIf { it.isNotBlank() }?.let { parameter("artist", it) }
        album?.takeIf { it.isNotBlank() }?.let { parameter("album", it) }
    }.expect()

    suspend fun getTrack(trackId: String): Track =
        client.get(url("/tracks/$trackId")) { auth() }.expect()

    suspend fun getTrackStats(trackId: String): TrackStatsResponse =
        client.get(url("/tracks/$trackId/stats")) { auth() }.expect()

    suspend fun updateTrack(trackId: String, update: TrackUpdateRequest): Track =
        client.patch(url("/tracks/$trackId")) {
            auth()
            contentType(ContentType.Application.Json)
            setBody(update)
        }.expect()

    suspend fun deleteTrack(trackId: String, deleteFile: Boolean = true) =
        client.delete(url("/tracks/$trackId")) {
            auth()
            parameter("delete_file", deleteFile)
        }.expectOk()

    suspend fun likedTracks(limit: Int = 200, offset: Int = 0): LikedTrackListResponse =
        client.get(url("/tracks/liked")) {
            auth()
            parameter("limit", limit)
            parameter("offset", offset)
        }.expect()

    suspend fun likeTrack(trackId: String): LikedTrackItem =
        client.put(url("/tracks/$trackId/like")) { auth() }.expect()

    suspend fun unlikeTrack(trackId: String) =
        client.delete(url("/tracks/$trackId/like")) { auth() }.expectOk()

    suspend fun recordPlay(trackId: String, event: PlaybackEventRequest = PlaybackEventRequest()) =
        client.post(url("/tracks/$trackId/plays")) {
            auth()
            contentType(ContentType.Application.Json)
            setBody(event)
        }.expectOk()

    suspend fun recentPlays(limit: Int = 50, offset: Int = 0): PlaybackEventListResponse =
        client.get(url("/tracks/recent")) {
            auth()
            parameter("limit", limit)
            parameter("offset", offset)
        }.expect()

    suspend fun listArtists(query: String? = null, limit: Int = 200, offset: Int = 0): ArtistListResponse =
        client.get(url("/tracks/artists")) {
            auth()
            parameter("limit", limit)
            parameter("offset", offset)
            query?.takeIf { it.isNotBlank() }?.let { parameter("q", it) }
        }.expect()

    suspend fun listAlbums(query: String? = null, limit: Int = 200, offset: Int = 0): AlbumListResponse =
        client.get(url("/tracks/albums")) {
            auth()
            parameter("limit", limit)
            parameter("offset", offset)
            query?.takeIf { it.isNotBlank() }?.let { parameter("q", it) }
        }.expect()

    suspend fun cacheStats(): CacheStatsResponse =
        client.get(url("/tracks/cache/stats")) { auth() }.expect()

    // ── Playback state ──────────────────────────────────────────────────

    suspend fun getPlaybackState(): PlaybackStateResponse =
        client.get(url("/playback/state")) { auth() }.expect()

    suspend fun updatePlaybackState(state: PlaybackStateUpdateRequest): PlaybackStateResponse =
        client.put(url("/playback/state")) {
            auth()
            contentType(ContentType.Application.Json)
            setBody(state)
        }.expect()

    suspend fun clearPlaybackState() =
        client.delete(url("/playback/state")) { auth() }.expectOk()

    // ── Playlists ───────────────────────────────────────────────────────

    suspend fun listPlaylists(limit: Int = 100, offset: Int = 0): PlaylistListResponse =
        client.get(url("/playlists")) {
            auth()
            parameter("limit", limit)
            parameter("offset", offset)
        }.expect()

    suspend fun createPlaylist(name: String): PlaylistDetail =
        client.post(url("/playlists")) {
            auth()
            contentType(ContentType.Application.Json)
            setBody(PlaylistCreateRequest(name))
        }.expect()

    suspend fun getPlaylist(playlistId: String): PlaylistDetail =
        client.get(url("/playlists/$playlistId")) { auth() }.expect()

    suspend fun renamePlaylist(playlistId: String, name: String): PlaylistDetail =
        client.patch(url("/playlists/$playlistId")) {
            auth()
            contentType(ContentType.Application.Json)
            setBody(PlaylistUpdateRequest(name))
        }.expect()

    suspend fun deletePlaylist(playlistId: String) =
        client.delete(url("/playlists/$playlistId")) { auth() }.expectOk()

    suspend fun addTrackToPlaylist(playlistId: String, trackId: String): PlaylistDetail =
        client.post(url("/playlists/$playlistId/tracks")) {
            auth()
            contentType(ContentType.Application.Json)
            setBody(PlaylistTrackAddRequest(trackId))
        }.expect()

    suspend fun reorderPlaylist(playlistId: String, trackIds: List<String>): PlaylistDetail =
        client.put(url("/playlists/$playlistId/tracks/order")) {
            auth()
            contentType(ContentType.Application.Json)
            setBody(PlaylistTrackOrderRequest(trackIds))
        }.expect()

    suspend fun removeTrackFromPlaylist(playlistId: String, trackId: String): PlaylistDetail =
        client.delete(url("/playlists/$playlistId/tracks/$trackId")) { auth() }.expect()

    // ── Catalog (self-service Lidarr acquisition) ───────────────────────

    suspend fun catalogSearch(query: String, kind: String = "artist"): CatalogSearchResponse =
        client.get(url("/catalog/search?kind=$kind&q=${query.encodeURLParameter()}")) { auth() }.expect()

    suspend fun catalogAdd(request: CatalogAddRequest): CatalogRequestListResponse =
        client.post(url("/catalog/add")) {
            auth()
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expect()

    suspend fun catalogRequests(): CatalogRequestListResponse =
        client.get(url("/catalog/requests")) { auth() }.expect()

    // ── Per-user libraries ──────────────────────────────────────────────

    suspend fun listLibraries(limit: Int = 100, offset: Int = 0): LibraryListResponse =
        client.get(url("/libraries")) {
            auth()
            parameter("limit", limit)
            parameter("offset", offset)
        }.expect()

    suspend fun createLibrary(name: String): LibraryDetail =
        client.post(url("/libraries")) {
            auth()
            contentType(ContentType.Application.Json)
            setBody(LibraryCreateRequest(name))
        }.expect()

    suspend fun getLibrary(libraryId: String): LibraryDetail =
        client.get(url("/libraries/$libraryId")) { auth() }.expect()

    suspend fun addTrackToLibrary(libraryId: String, trackId: String): LibraryDetail =
        client.post(url("/libraries/$libraryId/tracks")) {
            auth()
            contentType(ContentType.Application.Json)
            setBody(LibraryTrackAddRequest(trackId))
        }.expect()

    suspend fun removeTrackFromLibrary(libraryId: String, trackId: String): LibraryDetail =
        client.delete(url("/libraries/$libraryId/tracks/$trackId")) { auth() }.expect()

    suspend fun deleteLibrary(libraryId: String) =
        client.delete(url("/libraries/$libraryId")) { auth() }.expectOk()

    // ── Imports ─────────────────────────────────────────────────────────

    suspend fun listImports(status: String? = null, limit: Int = 50, offset: Int = 0): ImportListResponse =
        client.get(url("/imports")) {
            auth()
            parameter("limit", limit)
            parameter("offset", offset)
            status?.takeIf { it.isNotBlank() }?.let { parameter("status", it) }
        }.expect()

    suspend fun getImport(importId: String): ImportRecord =
        client.get(url("/imports/$importId")) { auth() }.expect()

    suspend fun cancelImport(importId: String, deleteFiles: Boolean = true): ImportRecord =
        client.post(url("/imports/$importId/cancel")) {
            auth()
            parameter("delete_files", deleteFiles)
        }.expect()

    suspend fun retryImport(importId: String, deleteFiles: Boolean = true): ImportRecord =
        client.post(url("/imports/$importId/retry")) {
            auth()
            parameter("delete_files", deleteFiles)
        }.expect()

    // ── Recommendations ─────────────────────────────────────────────────

    suspend fun recommendationsForTrack(
        trackId: String,
        localLimit: Int = 12,
        externalLimit: Int = 0,
    ): RecommendationResponse = client.get(url("/recommendations/tracks/$trackId")) {
        auth()
        parameter("local_limit", localLimit)
        parameter("external_limit", externalLimit)
    }.expect()

    suspend fun personalizedHome(
        localLimit: Int = 24,
        mixCount: Int = 4,
        mixSize: Int = 12,
    ): PersonalizedHomeResponse = client.get(url("/recommendations/personalized")) {
        auth()
        parameter("local_limit", localLimit)
        parameter("mix_count", mixCount)
        parameter("mix_size", mixSize)
    }.expect()

    // ── Library summary ─────────────────────────────────────────────────

    suspend fun librarySummary(): LibrarySummaryResponse =
        client.get(url("/library/summary")) { auth() }.expect()

    // ── Sync ────────────────────────────────────────────────────────────

    suspend fun listSyncActions(limit: Int = 200, includeApplied: Boolean = true): SyncActionListResponse =
        client.get(url("/sync/actions")) {
            auth()
            parameter("limit", limit)
            parameter("include_applied", includeApplied)
        }.expect()

    // ── Raw download (offline tracks, updater payloads) ─────────────────

    /** Streams any authenticated GET to a file consumer; used by DownloadManager. */
    suspend fun rawGet(fullUrl: String, useAuth: Boolean = true): HttpResponse =
        client.get(fullUrl) { if (useAuth) auth() }

    suspend fun headStream(trackId: String): HttpResponse =
        client.head(streamUrl(trackId)) { auth() }
}

private fun HttpRequestBuilder.parameter(name: String, value: Any?) {
    url.parameters.append(name, value.toString())
}
