package pl.mekamb.music

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaMetadata
import android.media.MediaPlayer
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.net.Uri
import android.os.Binder
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.util.Locale
import java.util.concurrent.CopyOnWriteArraySet
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

enum class RepeatMode(val label: String) {
    Off("Repeat Off"),
    All("Repeat All"),
    One("Repeat One");

    val isActive: Boolean get() = this != Off
}

/** Lightweight track model the playback engine and service work with, decoupled from the UI. */
data class PlaybackTrack(
    val id: String,
    val title: String,
    val artist: String?,
    val album: String?,
    val originalFilename: String?,
    val mediaType: String?,
    val durationSeconds: Double?
) {
    val displayArtist: String get() = artist?.takeIf { it.isNotBlank() } ?: "Unknown Artist"
    val displayAlbum: String get() = album?.takeIf { it.isNotBlank() } ?: "Unknown Album"
}

/**
 * Process-scoped playback engine. It owns the [MediaPlayer] and the whole queue/next/autoplay
 * pipeline, using the application context, so playback keeps running after the Activity that
 * started it is destroyed. A foreground [MediaPlaybackService] keeps the process alive and mirrors
 * this state to a MediaSession + media notification.
 */
object Playback {
    fun interface Listener {
        fun onPlaybackStateChanged()
    }

    private lateinit var app: Context
    private val executor = Executors.newSingleThreadExecutor()
    private val ioExecutor = Executors.newFixedThreadPool(2)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val requestId = AtomicInteger(0)
    private val listeners = CopyOnWriteArraySet<Listener>()

    var queue: List<PlaybackTrack> = emptyList(); private set
    var currentIndex: Int = -1; private set
    var currentTrack: PlaybackTrack? = null; private set
    var isPlaying: Boolean = false; private set
    var repeatMode: RepeatMode = RepeatMode.Off; private set
    var shuffle: Boolean = false; private set
    /// Short codec label ("FLAC"/"AAC"/…) of the track currently playing.
    var currentCodecLabel: String? = null; private set

    /** Full library snapshot pushed by the UI, used only for the offline autoplay fallback. */
    private var library: List<PlaybackTrack> = emptyList()

    private var player: MediaPlayer? = null
    private var playSessionTrack: PlaybackTrack? = null
    private var playSessionMaxMs: Int = 0
    private var autoplayStash: List<PlaybackTrack> = emptyList()
    private var autoplayStashSeedId: String? = null

    private var audioManager: AudioManager? = null
    private var focusRequest: AudioFocusRequest? = null
    private var pausedByFocusLoss = false

    fun init(context: Context) {
        if (!::app.isInitialized) {
            app = context.applicationContext
            audioManager = app.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
        }
    }

    fun addListener(listener: Listener) { listeners.add(listener) }
    fun removeListener(listener: Listener) { listeners.remove(listener) }

    private fun notifyChanged() {
        mainHandler.post { listeners.forEach { it.onPlaybackStateChanged() } }
    }

    val positionMs: Int
        get() = runCatching { player?.currentPosition ?: 0 }.getOrDefault(0)
    val durationMs: Int
        get() = runCatching { player?.duration?.takeIf { it > 0 } ?: 0 }.getOrDefault(0)

    fun setLibrary(tracks: List<PlaybackTrack>) { library = tracks }

    fun setRepeat(mode: RepeatMode) {
        repeatMode = mode
        if (mode != RepeatMode.Off) {
            autoplayStash = emptyList()
            autoplayStashSeedId = null
        }
        notifyChanged()
        postPlaybackStateAsync()
    }

    fun setShuffle(enabled: Boolean) {
        shuffle = enabled
        notifyChanged()
        postPlaybackStateAsync()
    }

    fun play(newQueue: List<PlaybackTrack>, startIndex: Int) {
        val effectiveQueue = newQueue.ifEmpty { library }
        if (effectiveQueue.isEmpty()) return
        val index = startIndex.coerceIn(0, effectiveQueue.lastIndex)
        queue = effectiveQueue
        currentIndex = index
        startTrack(effectiveQueue[index])
    }

    private fun startTrack(track: PlaybackTrack) {
        val id = requestId.incrementAndGet()
        beginPlaySession(track)
        currentTrack = track
        currentCodecLabel = codecLabel(track)
        isPlaying = false
        notifyChanged()
        // Keep the process alive with a foreground service for the duration of playback.
        startService()
        ioExecutor.execute {
            val source = runCatching { resolvePlayableFile(track) }.getOrNull()
            mainHandler.post {
                if (id != requestId.get()) return@post
                if (source == null) {
                    isPlaying = false
                    notifyChanged()
                    return@post
                }
                openPlayer(track, source, id)
            }
        }
    }

    private fun openPlayer(track: PlaybackTrack, file: File, id: Int) {
        player?.release()
        player = MediaPlayer().apply {
            setWakeMode(app, PowerManager.PARTIAL_WAKE_LOCK)
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .build()
            )
            setDataSource(file.absolutePath)
            setOnPreparedListener {
                if (id != requestId.get()) {
                    it.release()
                    return@setOnPreparedListener
                }
                if (!requestAudioFocus()) return@setOnPreparedListener
                it.start()
                Playback.isPlaying = true
                notifyChanged()
                postPlaybackStateAsync()
                prefetchAutoplayIfNeeded(track)
            }
            setOnCompletionListener {
                finalizePlaySession(naturalEnd = true)
                advanceAfterCompletion(track)
            }
            setOnErrorListener { failed, _, _ ->
                // The player is now in the Error state where even isPlaying throws;
                // drop it so the next play/toggle rebuilds the track instead of
                // poking a dead player.
                if (player === failed) player = null
                runCatching { failed.release() }
                Playback.isPlaying = false
                notifyChanged()
                true
            }
            prepareAsync()
        }
    }

    private fun advanceAfterCompletion(finished: PlaybackTrack) {
        when (repeatMode) {
            RepeatMode.One -> startTrack(finished)
            RepeatMode.All -> next()
            RepeatMode.Off -> {
                if (currentIndex >= 0 && currentIndex < queue.lastIndex) {
                    next()
                } else {
                    val continuation = autoplayContinuationForQueueEnd(finished, queue)
                    if (continuation.isNotEmpty()) {
                        queue = queue + continuation
                        currentIndex = queue.indexOfFirst { it.id == continuation.first().id }
                        startTrack(continuation.first())
                    } else {
                        isPlaying = false
                        notifyChanged()
                    }
                }
            }
        }
    }

    /**
     * MediaPlayer's transport calls (isPlaying/start/pause/seekTo) throw
     * IllegalStateException once the player has slipped into the Error state —
     * which is exactly where it lands after a failed stream (truncated download,
     * dropped connection, rejected token). Returns null for "player is broken"
     * so callers can rebuild instead of crashing the main thread.
     */
    private fun MediaPlayer.isPlayingSafe(): Boolean? = runCatching { isPlaying }.getOrNull()

    /** Drops a dead player and restarts the current track from scratch. */
    private fun recoverFromDeadPlayer() {
        player?.let { runCatching { it.release() } }
        player = null
        isPlaying = false
        currentTrack?.let { startTrack(it) }
    }

    fun toggle() {
        val current = player
        if (current == null) {
            currentTrack?.let { startTrack(it) }
            return
        }
        val playing = current.isPlayingSafe()
        if (playing == null) {
            recoverFromDeadPlayer()
            return
        }
        if (playing) {
            runCatching { current.pause() }
            isPlaying = false
            pausedByFocusLoss = false
        } else {
            if (!requestAudioFocus()) return
            if (runCatching { current.start() }.isFailure) {
                recoverFromDeadPlayer()
                return
            }
            isPlaying = true
        }
        notifyChanged()
        postPlaybackStateAsync()
    }

    fun resume() {
        val current = player ?: return currentTrack?.let { startTrack(it) } ?: Unit
        val playing = current.isPlayingSafe()
        if (playing == null) {
            recoverFromDeadPlayer()
            return
        }
        if (!playing) {
            if (!requestAudioFocus()) return
            if (runCatching { current.start() }.isFailure) {
                recoverFromDeadPlayer()
                return
            }
            isPlaying = true
            notifyChanged()
            postPlaybackStateAsync()
        }
    }

    fun pause() {
        val current = player ?: return
        // Called from audio-focus loss and becoming-noisy too: never restart here,
        // just make sure a dead player can't crash us.
        if (current.isPlayingSafe() == true) {
            runCatching { current.pause() }
            isPlaying = false
            notifyChanged()
            postPlaybackStateAsync()
        }
    }

    fun next() {
        val effective = queue.ifEmpty { library }
        if (effective.isEmpty()) return
        val nextIndex = if (shuffle && effective.size > 1) {
            effective.indices.filter { it != currentIndex }.random()
        } else {
            if (currentIndex < 0) 0 else (currentIndex + 1) % effective.size
        }
        queue = effective
        currentIndex = nextIndex
        startTrack(effective[nextIndex])
    }

    fun previous() {
        val effective = queue.ifEmpty { library }
        if (effective.isEmpty()) return
        val previousIndex = if (currentIndex <= 0) effective.lastIndex else currentIndex - 1
        queue = effective
        currentIndex = previousIndex
        startTrack(effective[previousIndex])
    }

    fun seekTo(ms: Int) {
        runCatching { player?.seekTo(ms.coerceAtLeast(0)) }
        notifyChanged()
        postPlaybackStateAsync()
    }

    fun stop() {
        requestId.incrementAndGet()
        finalizePlaySession(naturalEnd = false)
        abandonAudioFocus()
        player?.release()
        player = null
        isPlaying = false
        currentTrack = null
        notifyChanged()
    }

    // --- Skip / listen-ratio reporting -------------------------------------------------------

    private fun beginPlaySession(track: PlaybackTrack) {
        if (playSessionTrack?.id == track.id) return
        finalizePlaySession(naturalEnd = false)
        playSessionTrack = track
        playSessionMaxMs = 0
    }

    private fun finalizePlaySession(naturalEnd: Boolean) {
        val track = playSessionTrack ?: return
        playSessionTrack = null
        val durationMs = ((track.durationSeconds ?: 0.0) * 1000.0).toInt()
        val ratio: Double? = when {
            naturalEnd -> 1.0
            durationMs > 0 -> (playSessionMaxMs.toDouble() / durationMs.toDouble()).coerceIn(0.0, 1.0)
            else -> null
        }
        val completed = naturalEnd || (ratio ?: 0.0) >= 0.9
        playSessionMaxMs = 0
        postPlay(track, completed, ratio)
    }

    /** Called ~1/s by the service's ticker so the skip ratio reflects real listen time. */
    fun tickProgress() {
        val current = player ?: return
        // The ticker can race a player error; a dead player throws from isPlaying/
        // currentPosition, and a missed tick is harmless.
        runCatching {
            if (playSessionTrack?.id == currentTrack?.id && current.isPlaying) {
                playSessionMaxMs = maxOf(playSessionMaxMs, current.currentPosition)
            }
        }
    }

    // --- Autoplay continuation ---------------------------------------------------------------

    private fun prefetchAutoplayIfNeeded(track: PlaybackTrack) {
        if (repeatMode != RepeatMode.Off || !canUseApi()) {
            autoplayStash = emptyList()
            autoplayStashSeedId = null
            return
        }
        val index = queue.indexOfFirst { it.id == track.id }
        if (index < 0 || index != queue.lastIndex) {
            autoplayStash = emptyList()
            autoplayStashSeedId = null
            return
        }
        if (autoplayStashSeedId == track.id && autoplayStash.isNotEmpty()) return
        executor.execute {
            val fetched = runCatching { fetchAutoplayContinuation(track, queue) }.getOrNull()
            mainHandler.post {
                if (currentTrack?.id != track.id || fetched.isNullOrEmpty()) return@post
                val queueIds = queue.map { it.id }.toSet()
                autoplayStash = fetched.filter { !queueIds.contains(it.id) }
                autoplayStashSeedId = track.id
            }
        }
    }

    private fun autoplayContinuationForQueueEnd(seed: PlaybackTrack, current: List<PlaybackTrack>): List<PlaybackTrack> {
        val stashed = if (autoplayStashSeedId == seed.id) {
            autoplayStash.filter { candidate -> current.none { it.id == candidate.id } }
        } else {
            emptyList()
        }
        autoplayStash = emptyList()
        autoplayStashSeedId = null
        if (stashed.isNotEmpty()) return stashed
        val queueIds = current.map { it.id }.toSet()
        val sameArtist = library.filter { it.displayArtist == seed.displayArtist && !queueIds.contains(it.id) }
        val others = library.filter { !queueIds.contains(it.id) && it.displayArtist != seed.displayArtist }
        return (sameArtist + others).distinctBy { it.id }.take(20)
    }

    private fun fetchAutoplayContinuation(seed: PlaybackTrack, current: List<PlaybackTrack>): List<PlaybackTrack> {
        val excludeIds = current.takeLast(100).joinToString(",") { it.id }
        val path = "/recommendations/autoplay?seed_track_id=${encodePath(seed.id)}" +
            "&exclude=${encodeQuery(excludeIds)}&limit=25"
        val response = JSONObject(httpGet(path))
        val items = response.optJSONArray("tracks") ?: JSONArray()
        val result = mutableListOf<PlaybackTrack>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            val trackJson = item.optJSONObject("track") ?: continue
            parsePlaybackTrack(trackJson)?.let { result += it }
        }
        return result
    }

    // --- Networking / source resolution ------------------------------------------------------

    private fun prefs() = app.getSharedPreferences("mekamb_music_android", Context.MODE_PRIVATE)
    private fun apiToken() = prefs().getString("api_token", "") ?: ""

    private fun normalizedEndpoint(): String {
        val trimmed = (prefs().getString("api_endpoint", "") ?: "").trim().trimEnd('/')
        if (trimmed.isBlank()) return ""
        return if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) trimmed else "http://$trimmed"
    }

    private fun canUseApi(): Boolean = normalizedEndpoint().isNotBlank() && apiToken().isNotBlank()
    private fun endpointUrl(path: String): String? {
        val base = normalizedEndpoint()
        return if (base.isBlank()) null else base + path
    }

    private fun encodePath(value: String): String = Uri.encode(value)
    private fun encodeQuery(value: String): String = URLEncoder.encode(value, "UTF-8")

    private fun httpGet(path: String): String {
        val endpoint = endpointUrl(path) ?: throw IllegalStateException("bad endpoint")
        val connection = URL(endpoint).openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.connectTimeout = 20_000
        connection.readTimeout = 20_000
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty("Authorization", "Bearer ${apiToken()}")
        val status = connection.responseCode
        val payload = (if (status in 200..299) connection.inputStream else connection.errorStream)
            ?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (status !in 200..299) throw IllegalStateException("API error $status")
        return payload
    }

    private fun postPlay(track: PlaybackTrack, completed: Boolean, listenRatio: Double?) {
        if (!canUseApi()) return
        val body = JSONObject()
            .put("completed", completed)
            .put("listen_ratio", listenRatio ?: JSONObject.NULL)
            .put("source", "android")
            .toString()
        executor.execute {
            runCatching {
                val endpoint = endpointUrl("/tracks/${encodePath(track.id)}/plays") ?: return@runCatching
                val connection = URL(endpoint).openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.connectTimeout = 15_000
                connection.readTimeout = 15_000
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.setRequestProperty("Authorization", "Bearer ${apiToken()}")
                connection.outputStream.use { it.write(body.toByteArray()) }
                connection.responseCode
                connection.disconnect()
            }
        }
    }

    private fun postPlaybackStateAsync() {
        if (!canUseApi()) return
        val snapshotQueue = queue.ifEmpty { library }
        val payload = JSONObject()
            .put("current_track_id", currentTrack?.id ?: JSONObject.NULL)
            .put("position_seconds", (positionMs.toDouble() / 1000.0).coerceAtLeast(0.0))
            .put("is_playing", isPlaying)
            .put("repeat_mode", when (repeatMode) {
                RepeatMode.Off -> "off"
                RepeatMode.All -> "queue"
                RepeatMode.One -> "track"
            })
            .put("shuffle", shuffle)
            .put("active_device_id", "android-${android.os.Build.MODEL}")
            .put("active_device_name", android.os.Build.MODEL ?: "Android")
            .put("queue_track_ids", JSONArray().apply { snapshotQueue.forEach { put(it.id) } })
            .toString()
        executor.execute {
            runCatching {
                val endpoint = endpointUrl("/playback/state") ?: return@runCatching
                val connection = URL(endpoint).openConnection() as HttpURLConnection
                connection.requestMethod = "PUT"
                connection.connectTimeout = 15_000
                connection.readTimeout = 15_000
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.setRequestProperty("Authorization", "Bearer ${apiToken()}")
                connection.outputStream.use { it.write(payload.toByteArray()) }
                connection.responseCode
                connection.disconnect()
            }
        }
    }

    // ── Playback quality (Auto / AAC / Lossless) ─────────────────────────────────────────────

    private val losslessExtensions = setOf("flac", "wav", "wave", "aif", "aiff", "alac", "ape", "wv")

    private fun sourceExtension(track: PlaybackTrack): String {
        val fromName = track.originalFilename?.substringAfterLast('.', "")
            ?.lowercase(Locale.getDefault())
            ?.filter { it.isLetterOrDigit() }
            ?.takeIf { it.length in 2..5 }
        if (fromName != null) return fromName
        return when (track.mediaType?.lowercase(Locale.getDefault())) {
            "audio/flac", "audio/x-flac" -> "flac"
            "audio/wav", "audio/x-wav", "audio/wave" -> "wav"
            "audio/aiff", "audio/x-aiff" -> "aiff"
            "audio/mpeg" -> "mp3"
            "audio/mp4", "audio/aac", "audio/x-m4a" -> "m4a"
            "audio/ogg" -> "ogg"
            else -> ""
        }
    }

    private fun isLosslessSource(track: PlaybackTrack): Boolean =
        losslessExtensions.contains(sourceExtension(track))

    private fun isMeteredConnection(): Boolean {
        val manager = app.getSystemService(Context.CONNECTIVITY_SERVICE) as? android.net.ConnectivityManager
            ?: return false
        return manager.isActiveNetworkMetered
    }

    private fun wantsAac(): Boolean = when (prefs().getString("playback_quality", "auto")) {
        "aac" -> true
        "lossless" -> false
        else -> isMeteredConnection() // "auto"
    }

    /** The `format` query value to request for this track (only lossless sources are transcoded). */
    private fun streamFormat(track: PlaybackTrack): String? =
        if (wantsAac() && isLosslessSource(track)) "aac" else null

    private fun codecLabel(track: PlaybackTrack): String {
        if (offlineFile(track) != null) return sourceCodecLabel(track)
        if (streamFormat(track) == "aac") return "AAC"
        return sourceCodecLabel(track)
    }

    private fun sourceCodecLabel(track: PlaybackTrack): String = when (sourceExtension(track)) {
        "flac" -> "FLAC"
        "wav", "wave" -> "WAV"
        "aif", "aiff" -> "AIFF"
        "alac" -> "ALAC"
        "mp3" -> "MP3"
        "m4a", "aac", "mp4" -> "AAC"
        "" -> "AUDIO"
        else -> sourceExtension(track).uppercase(Locale.getDefault())
    }

    /** Resolves a playable local file: an existing offline/cache copy, else downloads to cache. */
    private fun resolvePlayableFile(track: PlaybackTrack): File {
        offlineFile(track)?.let { return it }
        val format = streamFormat(track)
        val cacheDir = File(app.cacheDir, "playback").apply { mkdirs() }
        // Namespace the cache by format so an AAC copy and a lossless copy never collide.
        val prefix = if (format == "aac") "aac-" else ""
        val output = File(cacheDir, "$prefix${track.id}.${if (format == "aac") "m4a" else playbackExtension(track)}")
        if (output.isFile && output.length() > 0L) return output
        val query = if (format == "aac") "?format=aac" else ""
        val endpoint = endpointUrl("/tracks/${encodePath(track.id)}/stream$query")
            ?: throw IllegalStateException("bad endpoint")
        val temp = File(cacheDir, "${output.name}.tmp")
        val connection = URL(endpoint).openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.connectTimeout = 20_000
        connection.readTimeout = 90_000
        connection.setRequestProperty("Accept", track.mediaType ?: "audio/*")
        connection.setRequestProperty("Authorization", "Bearer ${apiToken()}")
        val status = connection.responseCode
        if (status !in 200..299) {
            connection.disconnect()
            temp.delete()
            throw IllegalStateException("stream error $status")
        }
        connection.inputStream.use { input -> temp.outputStream().use { input.copyTo(it) } }
        connection.disconnect()
        if (!temp.renameTo(output)) {
            temp.copyTo(output, overwrite = true)
            temp.delete()
        }
        return output
    }

    private fun offlineFile(track: PlaybackTrack): File? {
        val dir = File(app.filesDir, "offline/tracks")
        val digest = MessageDigest.getInstance("SHA-256").digest(track.id.toByteArray(Charsets.UTF_8))
        val name = digest.joinToString("") { "%02x".format(it) } + "." + playbackExtension(track)
        val file = File(dir, name)
        return file.takeIf { it.isFile && it.length() > 0L }
    }

    private fun playbackExtension(track: PlaybackTrack): String {
        val filenameExtension = track.originalFilename
            ?.substringAfterLast('.', "")
            ?.lowercase(Locale.getDefault())
            ?.filter { it.isLetterOrDigit() }
            ?.takeIf { it.length in 2..5 }
        if (filenameExtension != null) return filenameExtension
        return when (track.mediaType?.lowercase(Locale.getDefault())) {
            "audio/mpeg" -> "mp3"
            "audio/mp4", "audio/aac", "audio/x-m4a" -> "m4a"
            "audio/flac", "audio/x-flac" -> "flac"
            "audio/ogg" -> "ogg"
            "audio/wav", "audio/x-wav" -> "wav"
            else -> "audio"
        }
    }

    private fun parsePlaybackTrack(item: JSONObject): PlaybackTrack? {
        val id = item.optString("id").takeIf { it.isNotBlank() } ?: return null
        fun str(name: String) = item.optString(name).takeIf { it.isNotBlank() && it != "null" }
        return PlaybackTrack(
            id = id,
            title = str("title") ?: str("original_filename") ?: "Untitled",
            artist = str("artist"),
            album = str("album"),
            originalFilename = str("original_filename"),
            mediaType = str("media_type"),
            durationSeconds = item.optDouble("duration_seconds").takeIf { !it.isNaN() }
        )
    }

    /** Fetches artwork for the notification/lock screen. */
    fun fetchArtwork(trackId: String): Bitmap? {
        val endpoint = endpointUrl("/tracks/${encodePath(trackId)}/artwork") ?: return null
        return runCatching {
            val connection = URL(endpoint).openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 12_000
            connection.readTimeout = 15_000
            connection.setRequestProperty("Authorization", "Bearer ${apiToken()}")
            if (connection.responseCode !in 200..299) {
                connection.disconnect()
                return@runCatching null
            }
            val bytes = connection.inputStream.use { it.readBytes() }
            connection.disconnect()
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
        }.getOrNull()
    }

    // --- Audio focus -------------------------------------------------------------------------

    private val focusListener = AudioManager.OnAudioFocusChangeListener { change ->
        when (change) {
            AudioManager.AUDIOFOCUS_LOSS -> pause()
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> {
                if (isPlaying) { pausedByFocusLoss = true; pause() }
            }
            AudioManager.AUDIOFOCUS_GAIN -> {
                if (pausedByFocusLoss) { pausedByFocusLoss = false; resume() }
            }
        }
    }

    private fun requestAudioFocus(): Boolean {
        val manager = audioManager ?: return true
        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .build()
            )
            .setOnAudioFocusChangeListener(focusListener)
            .build()
        focusRequest = request
        return manager.requestAudioFocus(request) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
    }

    private fun abandonAudioFocus() {
        val manager = audioManager ?: return
        focusRequest?.let { manager.abandonAudioFocusRequest(it) }
        focusRequest = null
    }

    private fun startService() {
        val intent = Intent(app, MediaPlaybackService::class.java)
        runCatching { app.startForegroundService(intent) }
    }
}

/**
 * Foreground service that keeps the process alive during playback and exposes a MediaSession +
 * media-style notification (lock-screen / Bluetooth / headset controls and artwork). All controls
 * forward to [Playback]; the notification and session are rebuilt whenever engine state changes.
 */
class MediaPlaybackService : Service(), Playback.Listener {
    private lateinit var session: MediaSession
    private lateinit var notificationManager: NotificationManager
    private val handler = Handler(Looper.getMainLooper())
    private var artworkTrackId: String? = null
    private var artwork: Bitmap? = null
    private var startedForeground = false

    private val ticker = object : Runnable {
        override fun run() {
            Playback.tickProgress()
            updateSessionState()
            if (Playback.isPlaying) handler.postDelayed(this, 1000)
        }
    }

    private val becomingNoisyReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == AudioManager.ACTION_AUDIO_BECOMING_NOISY) Playback.pause()
        }
    }

    override fun onBind(intent: Intent?): IBinder = LocalBinder()
    inner class LocalBinder : Binder()

    override fun onCreate() {
        super.onCreate()
        Playback.init(this)
        notificationManager = getSystemService(NotificationManager::class.java)
        createChannel()
        session = MediaSession(this, "MekambMusic").apply {
            setCallback(object : MediaSession.Callback() {
                override fun onPlay() = Playback.resume()
                override fun onPause() = Playback.pause()
                override fun onSkipToNext() = Playback.next()
                override fun onSkipToPrevious() = Playback.previous()
                override fun onStop() { Playback.stop() }
                override fun onSeekTo(pos: Long) = Playback.seekTo(pos.toInt())
            })
            isActive = true
        }
        val noisyFilter = IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY)
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            registerReceiver(becomingNoisyReceiver, noisyFilter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(becomingNoisyReceiver, noisyFilter)
        }
        Playback.addListener(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_TOGGLE -> Playback.toggle()
            ACTION_NEXT -> Playback.next()
            ACTION_PREV -> Playback.previous()
            ACTION_STOP -> Playback.stop()
        }
        // startForegroundService requires startForeground quickly; always post the notification.
        updateNotification(force = true)
        if (Playback.currentTrack == null && !Playback.isPlaying) stopSelfSafely()
        return START_STICKY
    }

    override fun onPlaybackStateChanged() {
        updateSessionState()
        if (Playback.currentTrack == null && !Playback.isPlaying) {
            stopSelfSafely()
        } else {
            updateNotification(force = false)
            if (Playback.isPlaying) {
                handler.removeCallbacks(ticker)
                handler.post(ticker)
            }
        }
    }

    private fun updateSessionState() {
        val track = Playback.currentTrack
        session.setMetadata(
            MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, track?.title ?: "")
                .putString(MediaMetadata.METADATA_KEY_ARTIST, track?.displayArtist ?: "")
                .putString(MediaMetadata.METADATA_KEY_ALBUM, track?.displayAlbum ?: "")
                .putLong(MediaMetadata.METADATA_KEY_DURATION, Playback.durationMs.toLong())
                .apply { artwork?.let { putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, it) } }
                .build()
        )
        val state = if (Playback.isPlaying) PlaybackState.STATE_PLAYING else PlaybackState.STATE_PAUSED
        session.setPlaybackState(
            PlaybackState.Builder()
                .setActions(
                    PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PAUSE or
                        PlaybackState.ACTION_PLAY_PAUSE or PlaybackState.ACTION_SKIP_TO_NEXT or
                        PlaybackState.ACTION_SKIP_TO_PREVIOUS or PlaybackState.ACTION_SEEK_TO or
                        PlaybackState.ACTION_STOP
                )
                .setState(state, Playback.positionMs.toLong(), if (Playback.isPlaying) 1f else 0f)
                .build()
        )
    }

    private fun updateNotification(force: Boolean) {
        val track = Playback.currentTrack
        ensureArtwork(track?.id)
        val notification = buildNotification(track)
        if (!startedForeground || force) {
            if (android.os.Build.VERSION.SDK_INT >= 29) {
                startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
            startedForeground = true
        } else {
            notificationManager.notify(NOTIFICATION_ID, notification)
        }
    }

    private fun buildNotification(track: PlaybackTrack?): Notification {
        val contentIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val playPauseIcon = if (Playback.isPlaying) android.R.drawable.ic_media_pause else android.R.drawable.ic_media_play
        val playPauseTitle = if (Playback.isPlaying) "Pause" else "Play"
        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_tab_library)
            .setContentTitle(track?.title ?: "Mekamb Music")
            .setContentText(track?.let { "${it.displayArtist} · ${it.displayAlbum}" } ?: "")
            .setLargeIcon(artwork)
            .setContentIntent(contentIntent)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setOngoing(Playback.isPlaying)
            .addAction(Notification.Action.Builder(android.R.drawable.ic_media_previous, "Previous", serviceAction(ACTION_PREV)).build())
            .addAction(Notification.Action.Builder(playPauseIcon, playPauseTitle, serviceAction(ACTION_TOGGLE)).build())
            .addAction(Notification.Action.Builder(android.R.drawable.ic_media_next, "Next", serviceAction(ACTION_NEXT)).build())
            .setStyle(
                Notification.MediaStyle()
                    .setMediaSession(session.sessionToken)
                    .setShowActionsInCompactView(0, 1, 2)
            )
            .build()
    }

    private fun ensureArtwork(trackId: String?) {
        if (trackId == null) { artwork = null; artworkTrackId = null; return }
        if (trackId == artworkTrackId) return
        artworkTrackId = trackId
        artwork = null
        Thread {
            val bitmap = Playback.fetchArtwork(trackId)
            handler.post {
                if (artworkTrackId == trackId && bitmap != null) {
                    artwork = bitmap
                    updateSessionState()
                    if (startedForeground) notificationManager.notify(NOTIFICATION_ID, buildNotification(Playback.currentTrack))
                }
            }
        }.start()
    }

    private fun serviceAction(action: String): PendingIntent {
        val intent = Intent(this, MediaPlaybackService::class.java).setAction(action)
        return PendingIntent.getService(this, action.hashCode(), intent, PendingIntent.FLAG_IMMUTABLE)
    }

    private fun stopSelfSafely() {
        handler.removeCallbacks(ticker)
        stopForeground(STOP_FOREGROUND_REMOVE)
        startedForeground = false
        stopSelf()
    }

    private fun createChannel() {
        val channel = NotificationChannel(CHANNEL_ID, "Playback", NotificationManager.IMPORTANCE_LOW).apply {
            setShowBadge(false)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }
        notificationManager.createNotificationChannel(channel)
    }

    override fun onDestroy() {
        handler.removeCallbacks(ticker)
        Playback.removeListener(this)
        runCatching { unregisterReceiver(becomingNoisyReceiver) }
        session.isActive = false
        session.release()
        super.onDestroy()
    }

    companion object {
        private const val CHANNEL_ID = "mekamb_playback"
        private const val NOTIFICATION_ID = 1001
        const val ACTION_TOGGLE = "pl.mekamb.music.TOGGLE"
        const val ACTION_NEXT = "pl.mekamb.music.NEXT"
        const val ACTION_PREV = "pl.mekamb.music.PREV"
        const val ACTION_STOP = "pl.mekamb.music.STOP"
    }
}
