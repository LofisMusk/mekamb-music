package pl.mekamb.music.desktop

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import pl.mekamb.music.desktop.api.Track
import pl.mekamb.music.desktop.player.QueueMath
import pl.mekamb.music.desktop.player.RepeatMode

class QueueLogicTest {

    private fun track(id: String) = Track(id = id, title = "Track $id")

    private val queue = (1..5).map { track("t$it") }

    @Test
    fun `dedupe keeps first occurrence order`() {
        val input = listOf(track("a"), track("b"), track("a"), track("c"), track("b"))
        assertEquals(listOf("a", "b", "c"), QueueMath.dedupe(input).map { it.id })
    }

    @Test
    fun `shuffle pins current track first and keeps every element`() {
        val shuffled = QueueMath.shuffledPinningCurrent(queue, currentIndex = 2) { 0.42 }
        assertEquals("t3", shuffled.first().id, "current track must stay at index 0")
        assertEquals(queue.map { it.id }.toSet(), shuffled.map { it.id }.toSet())
        assertEquals(queue.size, shuffled.size)
    }

    @Test
    fun `shuffle of single element is stable`() {
        val single = listOf(track("only"))
        assertEquals(single.map { it.id }, QueueMath.shuffledPinningCurrent(single, 0) { 0.0 }.map { it.id })
    }

    @Test
    fun `nextIndex advances then stops when repeat off`() {
        assertEquals(1, QueueMath.nextIndex(size = 5, index = 0, repeat = RepeatMode.OFF))
        assertNull(QueueMath.nextIndex(size = 5, index = 4, repeat = RepeatMode.OFF))
    }

    @Test
    fun `nextIndex wraps when repeat queue`() {
        assertEquals(0, QueueMath.nextIndex(size = 5, index = 4, repeat = RepeatMode.QUEUE))
    }

    @Test
    fun `nextIndex stays on same track when repeat track`() {
        assertEquals(2, QueueMath.nextIndex(size = 5, index = 2, repeat = RepeatMode.TRACK))
    }

    @Test
    fun `manual next wraps only under repeat queue`() {
        assertNull(QueueMath.manualNextIndex(size = 5, index = 4, repeat = RepeatMode.OFF))
        assertEquals(0, QueueMath.manualNextIndex(size = 5, index = 4, repeat = RepeatMode.QUEUE))
        assertNull(QueueMath.manualNextIndex(size = 5, index = 4, repeat = RepeatMode.TRACK))
    }

    @Test
    fun `previous restarts current track past threshold`() {
        // Position beyond 3s → restart (return same index).
        assertEquals(3, QueueMath.previousTarget(size = 5, index = 3, positionSeconds = 10.0, repeat = RepeatMode.OFF))
    }

    @Test
    fun `previous steps back below threshold`() {
        assertEquals(2, QueueMath.previousTarget(size = 5, index = 3, positionSeconds = 1.0, repeat = RepeatMode.OFF))
    }

    @Test
    fun `previous at first track wraps under repeat queue`() {
        assertEquals(4, QueueMath.previousTarget(size = 5, index = 0, positionSeconds = 0.5, repeat = RepeatMode.QUEUE))
    }

    @Test
    fun `previous at first track without wrap restarts`() {
        assertEquals(0, QueueMath.previousTarget(size = 5, index = 0, positionSeconds = 0.5, repeat = RepeatMode.OFF))
    }

    @Test
    fun `empty queue yields no next or previous`() {
        assertNull(QueueMath.nextIndex(size = 0, index = 0, repeat = RepeatMode.QUEUE))
        assertNull(QueueMath.previousTarget(size = 0, index = 0, positionSeconds = 0.0, repeat = RepeatMode.OFF))
    }

    @Test
    fun `shuffle is a genuine permutation across rng values`() {
        var counter = 0
        val rng = { (counter++ % 7) / 7.0 }
        val shuffled = QueueMath.shuffledPinningCurrent(queue, currentIndex = 0, rng = rng)
        assertTrue(shuffled.map { it.id }.toSet() == queue.map { it.id }.toSet())
    }
}
