package pl.mekamb.music.data

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import pl.mekamb.music.Playback
import pl.mekamb.music.PlaybackTrack
import pl.mekamb.music.RepeatMode

data class PlaybackSnapshot(
    val currentTrack: PlaybackTrack? = null,
    val isPlaying: Boolean = false,
    val positionMs: Int = 0,
    val durationMs: Int = 0,
    val shuffle: Boolean = false,
    val repeatMode: RepeatMode = RepeatMode.Off,
    val codecLabel: String? = null,
    val queue: List<PlaybackTrack> = emptyList(),
    val currentIndex: Int = -1,
) {
    /** Remaining queue in play order, wrapping — used by the "Up Next" list and mini-player label. */
    val upNext: List<PlaybackTrack>
        get() {
            if (queue.isEmpty() || currentIndex < 0) return emptyList()
            return (1 until queue.size).map { offset -> queue[(currentIndex + offset) % queue.size] }
        }

    val nextTrack: PlaybackTrack? get() = upNext.firstOrNull()
}

/**
 * Bridges the process-scoped [Playback] singleton (untouched — it still owns MediaPlayer,
 * MediaSession, audio focus, offline files, and the foreground service) into a [StateFlow] Compose
 * screens can collect with `collectAsStateWithLifecycle()`. Registers exactly one
 * [Playback.Listener] and additionally ticks once a second while playing so the scrub bar advances
 * without every screen polling [Playback] directly.
 */
class PlaybackBridge(private val scope: CoroutineScope) {
    private val _state = MutableStateFlow(snapshot())
    val state: StateFlow<PlaybackSnapshot> = _state

    private val listener = Playback.Listener { _state.value = snapshot() }
    private var tickerJob: Job? = null

    init {
        Playback.addListener(listener)
        tickerJob = scope.launch {
            while (isActive) {
                delay(1000)
                if (Playback.isPlaying) _state.value = snapshot()
            }
        }
    }

    private fun snapshot() = PlaybackSnapshot(
        currentTrack = Playback.currentTrack,
        isPlaying = Playback.isPlaying,
        positionMs = Playback.positionMs,
        durationMs = Playback.durationMs,
        shuffle = Playback.shuffle,
        repeatMode = Playback.repeatMode,
        codecLabel = Playback.currentCodecLabel,
        queue = Playback.queue,
        currentIndex = Playback.currentIndex,
    )

    fun dispose() {
        Playback.removeListener(listener)
        tickerJob?.cancel()
    }
}
