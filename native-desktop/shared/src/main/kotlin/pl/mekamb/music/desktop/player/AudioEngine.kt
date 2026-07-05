package pl.mekamb.music.desktop.player

import java.nio.ShortBuffer
import java.nio.file.Path
import java.util.concurrent.Executors
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.AudioSystem
import javax.sound.sampled.DataLine
import javax.sound.sampled.FloatControl
import javax.sound.sampled.SourceDataLine
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import org.bytedeco.ffmpeg.global.avutil
import org.bytedeco.javacv.FFmpegFrameGrabber

/**
 * ffmpeg-backed audio playback engine. Decodes any codec ffmpeg supports (mp3, flac,
 * m4a/aac, ogg, opus, wav, ...) from either a local file or an authenticated HTTP stream,
 * normalizes to signed 16-bit PCM and feeds a javax.sound SourceDataLine.
 *
 * All decoding happens on a single dedicated daemon thread; the public API is thread-safe
 * and non-blocking (commands go through a channel). The blocking SourceDataLine.write
 * provides natural pacing of the decode loop.
 */
class AudioEngine {

    sealed interface Source {
        data class Remote(val url: String, val bearerToken: String) : Source
        data class Local(val path: Path) : Source
    }

    sealed interface EngineState {
        data object Idle : EngineState
        data object Loading : EngineState
        data object Playing : EngineState
        data object Paused : EngineState
        data object Ended : EngineState
        data class Error(val message: String) : EngineState
    }

    private sealed interface Command {
        data class Load(val source: Source, val autoPlay: Boolean) : Command
        data object Pause : Command
        data object Resume : Command
        data class Seek(val seconds: Double) : Command
        data class SetVolume(val volume01: Float) : Command
        data object Stop : Command
    }

    private val _state = MutableStateFlow<EngineState>(EngineState.Idle)
    val state: StateFlow<EngineState> = _state

    private val _positionSeconds = MutableStateFlow(0.0)
    val positionSeconds: StateFlow<Double> = _positionSeconds

    private val _durationSeconds = MutableStateFlow<Double?>(null)
    val durationSeconds: StateFlow<Double?> = _durationSeconds

    /** Invoked on the engine thread when a track plays to its natural end. */
    @Volatile
    var onTrackEnded: (() -> Unit)? = null

    private val commands = Channel<Command>(Channel.UNLIMITED)
    private val dispatcher = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "audio-engine").apply { isDaemon = true }
    }.asCoroutineDispatcher()
    private val scope = CoroutineScope(SupervisorJob() + dispatcher)

    @Volatile
    private var volume01: Float = 1.0f

    init {
        scope.launch { runLoop() }
    }

    fun load(source: Source, autoPlay: Boolean = true) {
        _state.value = EngineState.Loading
        commands.trySend(Command.Load(source, autoPlay))
    }

    fun pause() = commands.trySend(Command.Pause).let {}

    fun resume() = commands.trySend(Command.Resume).let {}

    fun seekTo(seconds: Double) = commands.trySend(Command.Seek(seconds)).let {}

    fun setVolume(volume: Float) {
        volume01 = volume.coerceIn(0f, 1f)
        commands.trySend(Command.SetVolume(volume01))
    }

    fun stop() = commands.trySend(Command.Stop).let {}

    fun release() {
        commands.trySend(Command.Stop)
        scope.cancel()
        dispatcher.close()
    }

    // ── Decode loop (engine thread only) ────────────────────────────────────

    private var grabber: FFmpegFrameGrabber? = null
    private var line: SourceDataLine? = null
    private var playing = false

    private suspend fun runLoop() {
        while (true) {
            val command = if (playing) commands.tryReceive().getOrNull() else commands.receive()
            try {
                when (command) {
                    is Command.Load -> handleLoad(command)
                    is Command.Pause -> {
                        line?.stop()
                        playing = false
                        if (_state.value is EngineState.Playing) _state.value = EngineState.Paused
                    }
                    is Command.Resume -> {
                        if (grabber != null) {
                            line?.start()
                            playing = true
                            _state.value = EngineState.Playing
                        }
                    }
                    is Command.Seek -> handleSeek(command.seconds)
                    is Command.SetVolume -> applyGain()
                    is Command.Stop -> teardown()
                    null -> {}
                }
            } catch (interrupted: InterruptedException) {
                throw interrupted
            } catch (failure: Exception) {
                _state.value = EngineState.Error(failure.message ?: failure.toString())
                teardown(keepState = true)
            }

            if (playing) {
                pumpOneFrame()
            }
        }
    }

    private fun handleLoad(command: Command.Load) {
        teardown()
        val target = when (val source = command.source) {
            is Source.Local -> source.path.toAbsolutePath().toString()
            is Source.Remote -> source.url
        }
        val newGrabber = FFmpegFrameGrabber(target)
        if (command.source is Source.Remote) {
            newGrabber.setOption(
                "headers",
                "Authorization: Bearer ${(command.source as Source.Remote).bearerToken}\r\n",
            )
            // Recover from transient network drops instead of ending the track early.
            newGrabber.setOption("reconnect", "1")
            newGrabber.setOption("reconnect_streamed", "1")
            newGrabber.setOption("reconnect_delay_max", "5")
        }
        newGrabber.sampleFormat = avutil.AV_SAMPLE_FMT_S16
        newGrabber.start()

        val sampleRate = if (newGrabber.sampleRate > 0) newGrabber.sampleRate else 44_100
        val channels = if (newGrabber.audioChannels > 0) newGrabber.audioChannels else 2
        val format = AudioFormat(sampleRate.toFloat(), 16, channels, true, false)
        val info = DataLine.Info(SourceDataLine::class.java, format)
        val newLine = AudioSystem.getLine(info) as SourceDataLine
        // ~400ms of buffered audio keeps position tracking close to what is audible.
        val bufferBytes = (sampleRate * channels * 2 * 0.4).toInt()
        newLine.open(format, bufferBytes)

        grabber = newGrabber
        line = newLine
        applyGain()

        val lengthMicros = newGrabber.lengthInTime
        _durationSeconds.value = if (lengthMicros > 0) lengthMicros / 1_000_000.0 else null
        _positionSeconds.value = 0.0

        if (command.autoPlay) {
            newLine.start()
            playing = true
            _state.value = EngineState.Playing
        } else {
            playing = false
            _state.value = EngineState.Paused
        }
    }

    private fun handleSeek(seconds: Double) {
        val activeGrabber = grabber ?: return
        val duration = _durationSeconds.value
        val clamped = when {
            seconds < 0 -> 0.0
            duration != null -> min(seconds, max(0.0, duration - 0.5))
            else -> seconds
        }
        activeGrabber.setAudioTimestamp((clamped * 1_000_000).toLong())
        line?.flush()
        _positionSeconds.value = clamped
    }

    private fun pumpOneFrame() {
        val activeGrabber = grabber ?: return
        val activeLine = line ?: return
        val frame = activeGrabber.grabSamples()
        if (frame == null) {
            activeLine.drain()
            playing = false
            _state.value = EngineState.Ended
            onTrackEnded?.invoke()
            return
        }
        val samples = frame.samples ?: return
        val buffer = samples[0] as? ShortBuffer ?: return
        val bytes = shortBufferToLittleEndianBytes(buffer)
        activeLine.write(bytes, 0, bytes.size)
        if (frame.timestamp > 0) {
            _positionSeconds.value = frame.timestamp / 1_000_000.0
        }
    }

    private fun applyGain() {
        val activeLine = line ?: return
        if (!activeLine.isControlSupported(FloatControl.Type.MASTER_GAIN)) return
        val control = activeLine.getControl(FloatControl.Type.MASTER_GAIN) as FloatControl
        val decibels = if (volume01 <= 0.001f) {
            control.minimum
        } else {
            (20.0 * log10(volume01.toDouble())).toFloat().coerceIn(control.minimum, control.maximum)
        }
        control.value = decibels
    }

    private fun teardown(keepState: Boolean = false) {
        playing = false
        runCatching { line?.stop() }
        runCatching { line?.flush() }
        runCatching { line?.close() }
        runCatching { grabber?.stop() }
        runCatching { grabber?.release() }
        line = null
        grabber = null
        if (!keepState) {
            _state.value = EngineState.Idle
            _positionSeconds.value = 0.0
            _durationSeconds.value = null
        }
    }

    private fun shortBufferToLittleEndianBytes(buffer: ShortBuffer): ByteArray {
        val slice = buffer.duplicate()
        val bytes = ByteArray(slice.remaining() * 2)
        var index = 0
        while (slice.hasRemaining()) {
            val sample = slice.get().toInt()
            bytes[index++] = (sample and 0xFF).toByte()
            bytes[index++] = ((sample shr 8) and 0xFF).toByte()
        }
        return bytes
    }
}
