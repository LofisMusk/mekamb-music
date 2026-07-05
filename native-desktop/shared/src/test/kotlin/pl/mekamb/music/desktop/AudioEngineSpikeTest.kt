package pl.mekamb.music.desktop

import com.sun.net.httpserver.HttpServer
import java.io.ByteArrayOutputStream
import java.net.InetSocketAddress
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.atomic.AtomicReference
import javax.sound.sampled.AudioFileFormat
import javax.sound.sampled.AudioFormat
import javax.sound.sampled.AudioInputStream
import javax.sound.sampled.AudioSystem
import kotlin.math.PI
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.runBlocking
import pl.mekamb.music.desktop.player.AudioEngine

/**
 * Spike-style integration test for the ffmpeg audio engine. Verifies:
 *  1. Local file decode runs to natural end (Ended state + onTrackEnded callback).
 *  2. HTTP streaming works and the Authorization header reaches the server.
 *
 * Requires audio output hardware; skipped automatically when none is available (CI).
 */
class AudioEngineSpikeTest {

    private fun audioAvailable(): Boolean = runCatching {
        val format = AudioFormat(44_100f, 16, 1, true, false)
        val info = javax.sound.sampled.DataLine.Info(
            javax.sound.sampled.SourceDataLine::class.java, format
        )
        AudioSystem.isLineSupported(info)
    }.getOrDefault(false)

    private fun writeSineWav(target: Path, seconds: Double = 1.2) {
        val sampleRate = 44_100
        val total = (sampleRate * seconds).toInt()
        val pcm = ByteArrayOutputStream()
        for (i in 0 until total) {
            val sample = (sin(2 * PI * 440.0 * i / sampleRate) * 8000).toInt()
            pcm.write(sample and 0xFF)
            pcm.write((sample shr 8) and 0xFF)
        }
        val bytes = pcm.toByteArray()
        val format = AudioFormat(sampleRate.toFloat(), 16, 1, true, false)
        AudioInputStream(bytes.inputStream(), format, (bytes.size / 2).toLong()).use { stream ->
            AudioSystem.write(stream, AudioFileFormat.Type.WAVE, target.toFile())
        }
    }

    @Test
    fun `decodes local wav to natural end`() = runBlocking {
        if (!audioAvailable()) return@runBlocking

        val wav = Files.createTempFile("mekamb-spike", ".wav")
        writeSineWav(wav)
        val engine = AudioEngine()
        try {
            var ended = false
            engine.onTrackEnded = { ended = true }
            engine.setVolume(0.02f)
            engine.load(AudioEngine.Source.Local(wav))

            withTimeout(15_000) {
                engine.state.first { it is AudioEngine.EngineState.Ended }
            }
            assertTrue(ended, "onTrackEnded callback should fire")
            assertTrue(engine.positionSeconds.value > 0.5, "position should have advanced")
        } finally {
            engine.release()
            Files.deleteIfExists(wav)
        }
    }

    @Test
    fun `streams over http with bearer auth header`() = runBlocking {
        if (!audioAvailable()) return@runBlocking

        val wav = Files.createTempFile("mekamb-spike-http", ".wav")
        writeSineWav(wav)
        val bytes = Files.readAllBytes(wav)
        val seenAuth = AtomicReference<String?>(null)

        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/stream") { exchange ->
            seenAuth.compareAndSet(null, exchange.requestHeaders.getFirst("Authorization"))
            exchange.responseHeaders.add("Content-Type", "audio/wav")
            exchange.sendResponseHeaders(200, bytes.size.toLong())
            exchange.responseBody.use { it.write(bytes) }
        }
        server.start()

        val engine = AudioEngine()
        try {
            engine.setVolume(0.02f)
            engine.load(
                AudioEngine.Source.Remote(
                    url = "http://127.0.0.1:${server.address.port}/stream",
                    bearerToken = "spike-test-token",
                )
            )
            withTimeout(20_000) {
                engine.state.first { it is AudioEngine.EngineState.Ended }
            }
            assertEquals("Bearer spike-test-token", seenAuth.get())
        } finally {
            engine.release()
            server.stop(0)
            Files.deleteIfExists(wav)
            // Give the engine thread a beat to finish teardown before JVM exit.
            delay(100)
        }
    }
}
