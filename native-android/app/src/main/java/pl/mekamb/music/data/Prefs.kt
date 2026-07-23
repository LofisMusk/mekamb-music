package pl.mekamb.music.data

import android.content.Context

/**
 * Thin wrapper over the same `SharedPreferences` file the old View-based UI and [pl.mekamb.music.Playback]
 * already use ("mekamb_music_android"), so existing installs keep their endpoint/token/offline
 * downloads across this rewrite. Key names for endpoint/token/quality are unchanged from
 * MainActivity.kt on purpose.
 */
class Prefs(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("mekamb_music_android", Context.MODE_PRIVATE)

    var apiEndpoint: String
        get() = prefs.getString("api_endpoint", "") ?: ""
        set(value) = prefs.edit().putString("api_endpoint", value).apply()

    /** Bearer credential sent on every request — the account session token from /auth/login. */
    var apiToken: String
        get() = prefs.getString("api_token", "") ?: ""
        set(value) = prefs.edit().putString("api_token", value).apply()

    var accountUsername: String
        get() = prefs.getString("account_username", "") ?: ""
        set(value) = prefs.edit().putString("account_username", value).apply()

    var accountEmail: String
        get() = prefs.getString("account_email", "") ?: ""
        set(value) = prefs.edit().putString("account_email", value).apply()

    /** Whether the signed-in account is an admin — gates the in-app approval panel. */
    var accountIsAdmin: Boolean
        get() = prefs.getBoolean("account_is_admin", false)
        set(value) = prefs.edit().putBoolean("account_is_admin", value).apply()

    /** "auto" | "aac" | "lossless" — read by Playback when building the stream URL. */
    var playbackQuality: String
        get() = prefs.getString("playback_quality", "auto") ?: "auto"
        set(value) = prefs.edit().putString("playback_quality", value).apply()

    /** New: prefetch the next queued track's stream so skips start instantly. */
    var prefetchQueuedTracks: Boolean
        get() = prefs.getBoolean("prefetch_queued_tracks", true)
        set(value) = prefs.edit().putBoolean("prefetch_queued_tracks", value).apply()

    /** New: allow offline downloads while on a metered/cellular connection. */
    var downloadOverCellular: Boolean
        get() = prefs.getBoolean("download_over_cellular", false)
        set(value) = prefs.edit().putBoolean("download_over_cellular", value).apply()

    val offlineRecordsJson: String
        get() = prefs.getString("offline_records_json", "[]") ?: "[]"

    fun saveOfflineRecordsJson(json: String) {
        prefs.edit().putString("offline_records_json", json).apply()
    }

    fun normalizedEndpoint(): String {
        val trimmed = apiEndpoint.trim().trimEnd('/')
        if (trimmed.isBlank()) return ""
        return if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) trimmed else "http://$trimmed"
    }

    fun canUseApi(): Boolean = normalizedEndpoint().isNotBlank() && apiToken.isNotBlank()

    fun clearSession() {
        apiToken = ""
        accountUsername = ""
        accountEmail = ""
        accountIsAdmin = false
    }
}
