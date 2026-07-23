package pl.mekamb.music.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class ApiException(message: String, val code: String? = null) : Exception(message)

/**
 * Suspend-function wrapper over the same raw `HttpURLConnection` approach the old
 * `MainActivity.request()` used — kept deliberately, per the migration plan, instead of adding
 * Retrofit/OkHttp-for-networking. Every call blocks the calling thread, so callers must invoke
 * these from `Dispatchers.IO` (this class does that internally via [withContext]).
 */
class ApiClient(private val prefs: Prefs) {

    private fun endpointUrl(path: String): String? {
        val base = prefs.normalizedEndpoint()
        return if (base.isBlank()) null else base + path
    }

    private fun encodeQuery(value: String): String = URLEncoder.encode(value, "UTF-8")
    private fun encodePath(value: String): String = android.net.Uri.encode(value)

    /** Raw JSON-string request, mirroring the previous MainActivity.request() error handling. */
    suspend fun request(
        path: String,
        method: String = "GET",
        body: String? = null,
        requiresAuth: Boolean = true,
    ): String = withContext(Dispatchers.IO) {
        val endpoint = endpointUrl(path) ?: throw ApiException("Bad API endpoint. Use http://IP:8000.")
        val connection = URL(endpoint).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 20_000
        connection.readTimeout = 20_000
        connection.setRequestProperty("Accept", "application/json")
        if (requiresAuth) {
            connection.setRequestProperty("Authorization", "Bearer ${prefs.apiToken}")
        }
        if (body != null) {
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            OutputStreamWriter(connection.outputStream).use { it.write(body) }
        }
        val status = connection.responseCode
        val stream = if (status in 200..299) connection.inputStream else connection.errorStream
        val payload = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (status !in 200..299) {
            var detailCode: String? = null
            var detailMessage: String? = null
            runCatching {
                when (val detail = JSONObject(payload).opt("detail")) {
                    is JSONObject -> {
                        detailCode = detail.optString("code").takeIf { it.isNotBlank() }
                        detailMessage = detail.optString("message").takeIf { it.isNotBlank() }
                    }
                    is String -> detailMessage = detail.takeIf { it.isNotBlank() }
                    else -> {}
                }
            }
            throw ApiException(detailMessage ?: "API error $status", detailCode)
        }
        payload
    }

    // ── Tracks ────────────────────────────────────────────────────────────────────────────────

    suspend fun loadAllTracks(): List<ApiTrack> {
        val loaded = mutableListOf<ApiTrack>()
        val limit = 100
        var offset = 0
        while (true) {
            val response = JSONObject(request("/tracks?limit=$limit&offset=$offset"))
            val items = response.optJSONArray("items") ?: JSONArray()
            loaded += parseTracks(items)
            if (items.length() < limit) break
            offset += limit
        }
        return loaded
    }

    suspend fun loadTracksByArtist(artist: String): List<ApiTrack> {
        val response = JSONObject(request("/tracks?artist=${encodeQuery(artist)}&limit=200"))
        return parseTracks(response.optJSONArray("items") ?: JSONArray())
    }

    suspend fun loadAllLikedTrackIds(): Set<String> {
        val liked = mutableSetOf<String>()
        val limit = 100
        var offset = 0
        while (true) {
            val response = JSONObject(request("/tracks/liked?limit=$limit&offset=$offset"))
            val items = response.optJSONArray("items") ?: JSONArray()
            for (index in 0 until items.length()) {
                val item = items.optJSONObject(index) ?: continue
                val track = item.optJSONObject("track") ?: continue
                track.optCleanString("id")?.let { liked += it }
            }
            if (items.length() < limit) break
            offset += limit
        }
        return liked
    }

    suspend fun loadRecentPlays(limit: Int = 60): List<ApiTrack> {
        val response = JSONObject(request("/tracks/recent?limit=$limit"))
        val items = response.optJSONArray("items") ?: JSONArray()
        val result = mutableListOf<ApiTrack>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            val trackJson = item.optJSONObject("track") ?: continue
            parseTrack(trackJson)?.let { result += it }
        }
        return result
    }

    suspend fun setLiked(trackId: String, liked: Boolean) {
        request("/tracks/${encodePath(trackId)}/like", method = if (liked) "PUT" else "DELETE")
    }

    suspend fun cacheStats(): CacheStats {
        val response = JSONObject(request("/tracks/cache/stats"))
        return CacheStats(
            totalTracks = response.optInt("total_tracks", 0),
            totalSizeMb = response.optDouble("total_size_mb", 0.0),
            staleTracks = response.optInt("stale_tracks", 0),
            cacheTtlDays = response.optInt("cache_ttl_days", 0),
        )
    }

    suspend fun cleanupCache() {
        request("/tracks/cache/cleanup", method = "POST")
    }

    fun artworkUrl(trackId: String): String? = endpointUrl("/tracks/${encodePath(trackId)}/artwork")

    // ── Playlists ─────────────────────────────────────────────────────────────────────────────

    suspend fun loadAllPlaylists(): List<Playlist> {
        val summaries = mutableListOf<Pair<String, String>>()
        val limit = 100
        var offset = 0
        while (true) {
            val response = JSONObject(request("/playlists?limit=$limit&offset=$offset"))
            val items = response.optJSONArray("items") ?: JSONArray()
            for (index in 0 until items.length()) {
                val item = items.optJSONObject(index) ?: continue
                val id = item.optCleanString("id") ?: continue
                summaries += id to (item.optCleanString("name") ?: "Playlist")
            }
            if (items.length() < limit) break
            offset += limit
        }
        return summaries
            .sortedBy { it.second.lowercase() }
            .map { (id, _) -> parsePlaylist(JSONObject(request("/playlists/${encodePath(id)}"))) }
    }

    suspend fun createPlaylist(name: String): Playlist {
        val body = JSONObject().put("name", name).toString()
        return parsePlaylist(JSONObject(request("/playlists", method = "POST", body = body)))
    }

    suspend fun deletePlaylist(id: String) {
        request("/playlists/${encodePath(id)}", method = "DELETE")
    }

    suspend fun addTrackToPlaylist(playlistId: String, trackId: String): Playlist {
        val body = JSONObject().put("track_id", trackId).toString()
        return parsePlaylist(JSONObject(request("/playlists/${encodePath(playlistId)}/tracks", method = "POST", body = body)))
    }

    suspend fun removeTrackFromPlaylist(playlistId: String, trackId: String): Playlist {
        return parsePlaylist(
            JSONObject(
                request("/playlists/${encodePath(playlistId)}/tracks/${encodePath(trackId)}", method = "DELETE"),
            ),
        )
    }

    private fun parsePlaylist(item: JSONObject): Playlist {
        val playlistTracks = mutableListOf<Pair<Int, ApiTrack>>()
        val items = item.optJSONArray("tracks") ?: JSONArray()
        for (index in 0 until items.length()) {
            val playlistTrack = items.optJSONObject(index) ?: continue
            val trackJson = playlistTrack.optJSONObject("track") ?: continue
            val track = parseTrack(trackJson) ?: continue
            playlistTracks += playlistTrack.optInt("position", index + 1) to track
        }
        return Playlist(
            id = item.optCleanString("id") ?: "",
            name = item.optCleanString("name") ?: "Playlist",
            tracks = playlistTracks.sortedBy { it.first }.map { it.second },
            updatedAt = item.optCleanString("updated_at"),
        )
    }

    // ── My Libraries (curated subsets) ───────────────────────────────────────────────────────

    suspend fun loadLibraries(): List<UserLibrary> {
        val response = JSONObject(request("/libraries?limit=100"))
        val items = response.optJSONArray("items") ?: JSONArray()
        val result = mutableListOf<UserLibrary>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            result += UserLibrary(
                id = item.optCleanString("id") ?: continue,
                name = item.optCleanString("name") ?: "Library",
                trackCount = item.optInt("track_count", 0),
            )
        }
        return result
    }

    suspend fun createLibrary(name: String) {
        request("/libraries", method = "POST", body = JSONObject().put("name", name).toString())
    }

    suspend fun addTrackToLibrary(libraryId: String, trackId: String) {
        request("/libraries/${encodePath(libraryId)}/tracks", method = "POST", body = JSONObject().put("track_id", trackId).toString())
    }

    // ── Recommendations / Daily Mixes ────────────────────────────────────────────────────────

    suspend fun personalizedRecommendations(localLimit: Int = 30, mixCount: Int = 6, mixSize: Int = 12): Pair<List<ApiTrack>, List<DailyMix>> {
        val response = JSONObject(
            request("/recommendations/personalized?local_limit=$localLimit&mix_count=$mixCount&mix_size=$mixSize"),
        )
        val recTracks = mutableListOf<ApiTrack>()
        val recItems = response.optJSONArray("recommended_tracks") ?: JSONArray()
        for (index in 0 until recItems.length()) {
            val item = recItems.optJSONObject(index) ?: continue
            val trackJson = item.optJSONObject("track") ?: item
            parseTrack(trackJson)?.let { recTracks += it }
        }
        val mixes = mutableListOf<DailyMix>()
        val mixItems = response.optJSONArray("daily_mixes") ?: JSONArray()
        for (index in 0 until mixItems.length()) {
            val mixJson = mixItems.optJSONObject(index) ?: continue
            val mixTracks = mutableListOf<ApiTrack>()
            val mixTrackItems = mixJson.optJSONArray("tracks") ?: JSONArray()
            for (trackIndex in 0 until mixTrackItems.length()) {
                val entry = mixTrackItems.optJSONObject(trackIndex) ?: continue
                val trackJson = entry.optJSONObject("track") ?: continue
                parseTrack(trackJson)?.let { mixTracks += it }
            }
            mixes += DailyMix(
                id = mixJson.optCleanString("id") ?: "mix-$index",
                title = mixJson.optCleanString("title") ?: "Daily Mix ${index + 1}",
                description = mixJson.optCleanString("description") ?: "",
                seedLabel = mixJson.optCleanString("seed_label"),
                tracks = mixTracks,
            )
        }
        return recTracks to mixes
    }

    // ── Imports ───────────────────────────────────────────────────────────────────────────────

    suspend fun loadImports(status: String? = null, limit: Int = 50, offset: Int = 0): List<ImportRecord> {
        val query = buildString {
            append("/imports?limit=$limit&offset=$offset")
            if (!status.isNullOrBlank()) append("&status=${encodeQuery(status)}")
        }
        val response = JSONObject(request(query))
        val items = response.optJSONArray("items") ?: JSONArray()
        val result = mutableListOf<ImportRecord>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            val id = item.optCleanString("id") ?: continue
            val uploader = item.optCleanString("uploader")
            val source = item.optCleanString("source")
            result += ImportRecord(
                id = id,
                source = source,
                torrentId = item.optCleanString("torrent_id"),
                uploader = uploader,
                status = ImportStatus.from(item.optCleanString("status") ?: "queued"),
                errorMessage = item.optCleanString("error_message"),
                createdAt = item.optCleanString("created_at"),
                updatedAt = item.optCleanString("updated_at"),
                title = uploader?.takeIf { it.isNotBlank() } ?: source?.takeIf { it.isNotBlank() } ?: "Import $id",
            )
        }
        return result
    }

    suspend fun cancelImport(id: String, deleteFiles: Boolean = false) {
        request("/imports/${encodePath(id)}/cancel?delete_files=$deleteFiles", method = "POST")
    }

    suspend fun retryImport(id: String, deleteFiles: Boolean = false) {
        request("/imports/${encodePath(id)}/retry?delete_files=$deleteFiles", method = "POST")
    }

    // ── Library summary (badge counts) ──────────────────────────────────────────────────────

    suspend fun librarySummary(): LibrarySummaryInfo {
        val response = JSONObject(request("/library/summary"))
        return LibrarySummaryInfo(
            activeImportCount = response.optInt("active_import_count", 0),
            failedImportCount = response.optInt("failed_import_count", 0),
        )
    }

    // ── Catalog (Add Music) ──────────────────────────────────────────────────────────────────

    suspend fun searchCatalog(kind: String, query: String): List<CatalogItem> {
        val response = JSONObject(request("/catalog/search?kind=$kind&q=${encodeQuery(query)}"))
        val items = response.optJSONArray("items") ?: JSONArray()
        val result = mutableListOf<CatalogItem>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            val foreignId = item.optCleanString("foreign_id") ?: continue
            result += CatalogItem(
                kind = item.optCleanString("kind") ?: "artist",
                foreignId = foreignId,
                title = item.optCleanString("title") ?: "Unknown",
                artist = item.optCleanString("artist"),
                artistForeignId = item.optCleanString("artist_foreign_id"),
                disambiguation = item.optCleanString("disambiguation"),
                year = item.optInt("year", -1).takeIf { it > 0 },
            )
        }
        return result
    }

    suspend fun addToCatalog(item: CatalogItem): List<CatalogRequestItem> {
        val body = JSONObject()
            .put("kind", item.kind)
            .put("foreign_id", item.foreignId)
            .put("title", item.title)
            .put("artist", item.artist)
            .put("artist_foreign_id", item.artistForeignId)
            .toString()
        val response = JSONObject(request("/catalog/add", method = "POST", body = body))
        return parseCatalogRequests(response.optJSONArray("items") ?: JSONArray())
    }

    suspend fun loadCatalogRequests(): List<CatalogRequestItem> {
        val response = JSONObject(request("/catalog/requests"))
        return parseCatalogRequests(response.optJSONArray("items") ?: JSONArray())
    }

    private fun parseCatalogRequests(items: JSONArray): List<CatalogRequestItem> {
        val result = mutableListOf<CatalogRequestItem>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            result += CatalogRequestItem(
                id = item.optCleanString("id") ?: continue,
                kind = item.optCleanString("kind") ?: "",
                foreignId = item.optCleanString("foreign_id") ?: "",
                title = item.optCleanString("title") ?: "Unknown",
                status = item.optCleanString("status") ?: "requested",
            )
        }
        return result
    }

    // ── Auth / Account ────────────────────────────────────────────────────────────────────────

    suspend fun login(identifier: String, password: String, deviceName: String): Pair<String, AccountInfo> {
        val body = JSONObject()
            .put("identifier", identifier)
            .put("password", password)
            .put("device_name", deviceName)
            .toString()
        val response = JSONObject(request("/auth/login", method = "POST", body = body, requiresAuth = false))
        return parseSession(response)
    }

    /** Returns a session only if the account was auto-approved; otherwise null + a message. */
    suspend fun register(email: String, username: String, password: String): Pair<Pair<String, AccountInfo>?, String?> {
        val body = JSONObject().put("email", email).put("username", username).put("password", password).toString()
        val response = JSONObject(request("/auth/register", method = "POST", body = body, requiresAuth = false))
        val token = response.optString("token").takeIf { it.isNotBlank() && it != "null" }
        val session = token?.let { parseSession(response) }
        return session to response.optString("message").takeIf { it.isNotBlank() }
    }

    /** Current account, used on launch to refresh admin/status (and detect a revoked session). */
    suspend fun me(): AccountInfo = parseAccount(JSONObject(request("/auth/me")))

    suspend fun logout() {
        runCatching { request("/auth/logout", method = "POST") }
    }

    suspend fun testConnection(): Boolean {
        request("/health", requiresAuth = false)
        return true
    }

    // ── Admin account approval ─────────────────────────────────────────────────────────────────

    suspend fun adminUsers(status: String? = null): List<AdminUser> {
        val query = if (status.isNullOrBlank()) "/admin/users" else "/admin/users?status=${encodeQuery(status)}"
        val response = JSONObject(request(query))
        val items = response.optJSONArray("users") ?: JSONArray()
        val result = mutableListOf<AdminUser>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            result += AdminUser(
                id = item.optCleanString("id") ?: continue,
                username = item.optCleanString("username") ?: "",
                email = item.optCleanString("email") ?: "",
                status = item.optCleanString("status") ?: "pending",
                isAdmin = item.optBoolean("is_admin", false),
            )
        }
        return result
    }

    suspend fun setUserApproval(id: String, approve: Boolean) {
        val action = if (approve) "approve" else "reject"
        request("/admin/users/${encodePath(id)}/$action", method = "POST")
    }

    private fun parseSession(response: JSONObject): Pair<String, AccountInfo> {
        val token = response.optString("token")
        return token to parseAccount(response.optJSONObject("user"))
    }

    private fun parseAccount(user: JSONObject?): AccountInfo = AccountInfo(
        username = user?.optString("username").orEmpty(),
        email = user?.optString("email").orEmpty(),
        isAdmin = user?.optBoolean("is_admin", false) ?: false,
    )

    // ── Shared parsing ────────────────────────────────────────────────────────────────────────

    private fun parseTracks(items: JSONArray): List<ApiTrack> {
        val parsed = mutableListOf<ApiTrack>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            parsed += parseTrack(item) ?: continue
        }
        return parsed
    }

    private fun parseTrack(item: JSONObject): ApiTrack? {
        val id = item.optCleanString("id") ?: return null
        return ApiTrack(
            id = id,
            title = item.optCleanString("title") ?: item.optCleanString("original_filename") ?: "Untitled",
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

fun JSONObject.optCleanString(name: String): String? =
    if (has(name) && !isNull(name)) optString(name).takeIf { it.isNotBlank() } else null

fun JSONObject.optNullableDouble(name: String): Double? =
    if (has(name) && !isNull(name)) optDouble(name).takeIf { !it.isNaN() } else null

fun JSONObject.optNullableLong(name: String): Long? =
    if (has(name) && !isNull(name)) optLong(name) else null
