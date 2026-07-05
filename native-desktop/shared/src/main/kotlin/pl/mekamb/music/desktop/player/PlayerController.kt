package pl.mekamb.music.desktop.player

import java.net.InetAddress
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import pl.mekamb.music.desktop.api.MekambApi
import pl.mekamb.music.desktop.api.PlaybackEventRequest
import pl.mekamb.music.desktop.api.PlaybackStateUpdateRequest
import pl.mekamb.music.desktop.api.Track
import pl.mekamb.music.desktop.data.DownloadManager
import pl.mekamb.music.desktop.data.SettingsStore

/**
 * Owns the playback queue, shuffle/repeat state and the AudioEngine. Resolves each track to an
 * offline file, a cached prefetch, or an authenticated remote stream, reports plays and playback
 * state to the backend, and continues with recommendations when the queue runs out (if enabled).
 */
class PlayerController(
    private val api: MekambApi,
    private val downloads: DownloadManager,
    private val settings: SettingsStore,
) {
    private val engine = AudioEngine()
    private val mainScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val ioScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val _queue = MutableStateFlow<List<Track>>(emptyList())
    val queue: StateFlow<List<Track>> = _queue

    private var originalOrder: List<Track> = emptyList()

    private val _currentIndex = MutableStateFlow(-1)
    val currentIndex: StateFlow<Int> = _currentIndex

    private val _currentTrack = MutableStateFlow<Track?>(null)
    val currentTrack: StateFlow<Track?> = _currentTrack

    private val _isPlaying = MutableStateFlow(false)
    val isPlaying: StateFlow<Boolean> = _isPlaying

    private val _shuffle = MutableStateFlow(false)
    val shuffleEnabled: StateFlow<Boolean> = _shuffle

    private val _repeat = MutableStateFlow(RepeatMode.OFF)
    val repeatMode: StateFlow<RepeatMode> = _repeat

    private val _volume = MutableStateFlow(settings.state.value.volume)
    val volume: StateFlow<Float> = _volume

    val positionSeconds: StateFlow<Double> = engine.positionSeconds
    val durationSeconds: StateFlow<Double?> = engine.durationSeconds

    private val deviceName: String =
        runCatching { InetAddress.getLocalHost().hostName }.getOrDefault("desktop")

    private var stateDebounceJob: Job? = null
    private var volumeDebounceJob: Job? = null

    init {
        engine.setVolume(_volume.value)
        engine.onTrackEnded = { mainScope.launch { handleTrackEnded() } }
        mainScope.launch {
            engine.state.collect { state ->
                _isPlaying.value = state is AudioEngine.EngineState.Playing
            }
        }
        // Heartbeat: keep the backend's playback state fresh while something is playing.
        mainScope.launch {
            while (true) {
                delay(15_000)
                if (_isPlaying.value && _currentTrack.value != null) pushStateNow()
            }
        }
    }

    // ── Playback commands ───────────────────────────────────────────────

    fun playTracks(tracks: List<Track>, startIndex: Int = 0) {
        val deduped = QueueMath.dedupe(tracks)
        if (deduped.isEmpty()) return
        originalOrder = deduped
        val start = startIndex.coerceIn(0, deduped.lastIndex)
        if (_shuffle.value) {
            _queue.value = QueueMath.shuffledPinningCurrent(deduped, start) { Math.random() }
            loadIndex(0, autoPlay = true)
        } else {
            _queue.value = deduped
            loadIndex(start, autoPlay = true)
        }
    }

    fun addToQueue(track: Track) {
        if (_queue.value.any { it.id == track.id }) return
        _queue.value = _queue.value + track
        originalOrder = originalOrder + track
        if (_currentIndex.value < 0) loadIndex(0, autoPlay = true)
        pushStateDebounced()
    }

    fun playNextInQueue(track: Track) {
        val insertAt = (_currentIndex.value + 1).coerceIn(0, _queue.value.size)
        _queue.value = _queue.value.toMutableList().apply { add(insertAt, track) }
        originalOrder = originalOrder + track
        if (_currentIndex.value < 0) loadIndex(0, autoPlay = true)
        pushStateDebounced()
    }

    fun removeFromQueue(index: Int) {
        if (index !in _queue.value.indices) return
        val removed = _queue.value[index]
        val next = _queue.value.toMutableList().apply { removeAt(index) }
        originalOrder = originalOrder.filterNot { it.id == removed.id }
        _queue.value = next
        when {
            index < _currentIndex.value -> _currentIndex.value -= 1
            index == _currentIndex.value -> {
                if (next.isEmpty()) stopPlayback()
                else loadIndex(index.coerceAtMost(next.lastIndex), autoPlay = _isPlaying.value)
            }
        }
        pushStateDebounced()
    }

    fun clearUpcoming() {
        val keep = (_currentIndex.value + 1).coerceIn(0, _queue.value.size)
        val kept = _queue.value.take(keep)
        val keptIds = kept.map { it.id }.toSet()
        _queue.value = kept
        originalOrder = originalOrder.filter { it.id in keptIds }
        pushStateDebounced()
    }

    fun jumpTo(index: Int) {
        if (index in _queue.value.indices) loadIndex(index, autoPlay = true)
    }

    fun togglePlayPause() {
        if (_currentIndex.value < 0) return
        if (_isPlaying.value) engine.pause() else engine.resume()
        pushStateDebounced()
    }

    fun next() {
        val target = QueueMath.manualNextIndex(_queue.value.size, _currentIndex.value, _repeat.value)
        if (target != null) loadIndex(target, autoPlay = true) else stopPlayback()
    }

    fun previous() {
        if (_currentIndex.value < 0) return
        val target = QueueMath.previousTarget(
            _queue.value.size, _currentIndex.value, positionSeconds.value, _repeat.value,
        ) ?: return
        if (target == _currentIndex.value) engine.seekTo(0.0) else loadIndex(target, autoPlay = true)
    }

    fun seekTo(seconds: Double) {
        engine.seekTo(seconds)
        pushStateDebounced()
    }

    fun setVolume(volume: Float) {
        val clamped = volume.coerceIn(0f, 1f)
        _volume.value = clamped
        engine.setVolume(clamped)
        volumeDebounceJob?.cancel()
        volumeDebounceJob = mainScope.launch {
            delay(400)
            settings.update { it.copy(volume = clamped) }
        }
    }

    fun toggleShuffle() {
        val enable = !_shuffle.value
        _shuffle.value = enable
        val current = _currentTrack.value
        if (enable) {
            _queue.value = QueueMath.shuffledPinningCurrent(
                _queue.value, _currentIndex.value.coerceAtLeast(0),
            ) { Math.random() }
            _currentIndex.value = if (_queue.value.isEmpty()) -1 else 0
        } else {
            _queue.value = originalOrder
            _currentIndex.value = originalOrder.indexOfFirst { it.id == current?.id }
        }
        pushStateDebounced()
    }

    fun cycleRepeat() {
        _repeat.value = when (_repeat.value) {
            RepeatMode.OFF -> RepeatMode.QUEUE
            RepeatMode.QUEUE -> RepeatMode.TRACK
            RepeatMode.TRACK -> RepeatMode.OFF
        }
        pushStateDebounced()
    }

    fun release() {
        runCatching { pushStateNow() }
        engine.release()
        mainScope.cancel()
        ioScope.cancel()
    }

    // ── Internals ───────────────────────────────────────────────────────

    private fun loadIndex(index: Int, autoPlay: Boolean) {
        val track = _queue.value.getOrNull(index) ?: return
        _currentIndex.value = index
        _currentTrack.value = track
        engine.load(resolveSource(track), autoPlay)
        onTrackStarted(track, index)
    }

    private fun resolveSource(track: Track): AudioEngine.Source {
        downloads.offlinePath(track.id)?.let { return AudioEngine.Source.Local(it) }
        downloads.cachedPath(track.id)?.let { return AudioEngine.Source.Local(it) }
        return AudioEngine.Source.Remote(api.streamUrl(track.id), api.currentToken())
    }

    private fun onTrackStarted(track: Track, index: Int) {
        ioScope.launch {
            runCatching { api.recordPlay(track.id, PlaybackEventRequest(source = "desktop")) }
        }
        _queue.value.getOrNull(index + 1)?.let { downloads.prefetchToCache(it) }
        pushStateNow()
    }

    private fun stopPlayback() {
        engine.stop()
        _isPlaying.value = false
        pushStateDebounced()
    }

    private suspend fun handleTrackEnded() {
        val repeat = _repeat.value
        if (repeat == RepeatMode.TRACK) {
            loadIndex(_currentIndex.value, autoPlay = true)
            return
        }
        val next = QueueMath.nextIndex(_queue.value.size, _currentIndex.value, repeat)
        if (next != null) {
            loadIndex(next, autoPlay = true)
            return
        }
        if (settings.state.value.autoplaySimilar) {
            autoplaySimilarOrStop()
        } else {
            stopPlayback()
        }
    }

    private suspend fun autoplaySimilarOrStop() {
        val lastId = _currentTrack.value?.id ?: return stopPlayback()
        val existing = _queue.value.map { it.id }.toSet()
        val fresh = withContext(Dispatchers.IO) {
            runCatching {
                api.recommendationsForTrack(lastId, localLimit = 12)
                    .localTracks.map { it.track }
                    .filter { it.id !in existing }
            }.getOrDefault(emptyList())
        }
        if (fresh.isEmpty()) {
            stopPlayback()
            return
        }
        _queue.value = _queue.value + fresh
        originalOrder = originalOrder + fresh
        loadIndex(_currentIndex.value + 1, autoPlay = true)
    }

    private fun pushStateDebounced() {
        stateDebounceJob?.cancel()
        stateDebounceJob = mainScope.launch {
            delay(2_000)
            pushStateNow()
        }
    }

    private fun pushStateNow() {
        val request = PlaybackStateUpdateRequest(
            currentTrackId = _currentTrack.value?.id,
            positionSeconds = positionSeconds.value,
            isPlaying = _isPlaying.value,
            repeatMode = when (_repeat.value) {
                RepeatMode.OFF -> "off"
                RepeatMode.QUEUE -> "queue"
                RepeatMode.TRACK -> "track"
            },
            shuffle = _shuffle.value,
            activeDeviceId = settings.state.value.deviceId,
            activeDeviceName = deviceName,
            queueTrackIds = _queue.value.map { it.id }.take(500),
        )
        ioScope.launch { runCatching { api.updatePlaybackState(request) } }
    }
}
