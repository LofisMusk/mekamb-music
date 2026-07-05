package pl.mekamb.music.desktop.player

import pl.mekamb.music.desktop.api.Track

enum class RepeatMode { OFF, QUEUE, TRACK }

/**
 * Pure queue/shuffle/repeat math, isolated from AudioEngine so it is unit-testable.
 */
object QueueMath {

    /** Threshold (seconds) below which "previous" goes to the prior track rather than restarting. */
    const val PREVIOUS_RESTART_THRESHOLD_SECONDS = 3.0

    /** De-duplicates by track id while preserving first-seen order. */
    fun dedupe(tracks: List<Track>): List<Track> {
        val seen = HashSet<String>(tracks.size)
        return tracks.filter { seen.add(it.id) }
    }

    /**
     * Returns a shuffled permutation of [queue] with the track at [currentIndex] pinned to
     * position 0, so the currently-playing track keeps playing. [rng] is injectable for tests.
     */
    fun shuffledPinningCurrent(
        queue: List<Track>,
        currentIndex: Int,
        rng: () -> Double,
    ): List<Track> {
        if (queue.size <= 1) return queue.toList()
        val current = queue.getOrNull(currentIndex)
        val rest = queue.filterIndexed { index, _ -> index != currentIndex }.toMutableList()
        // Fisher-Yates using the injected RNG.
        for (i in rest.indices.reversed()) {
            val j = (rng() * (i + 1)).toInt().coerceIn(0, i)
            val tmp = rest[i]; rest[i] = rest[j]; rest[j] = tmp
        }
        return if (current != null) listOf(current) + rest else rest
    }

    /**
     * The index of the next track to play given the current [index], queue [size] and [repeat].
     * Returns null when playback should stop (end of queue, no repeat).
     */
    fun nextIndex(size: Int, index: Int, repeat: RepeatMode): Int? {
        if (size <= 0) return null
        return when (repeat) {
            RepeatMode.TRACK -> index.coerceIn(0, size - 1)
            RepeatMode.QUEUE -> if (index + 1 < size) index + 1 else 0
            RepeatMode.OFF -> if (index + 1 < size) index + 1 else null
        }
    }

    /**
     * The index for a manual "next" press: wraps under QUEUE, advances (or null at end) otherwise.
     * TRACK is treated as a normal advance for a manual skip.
     */
    fun manualNextIndex(size: Int, index: Int, repeat: RepeatMode): Int? {
        if (size <= 0) return null
        return if (index + 1 < size) index + 1
        else if (repeat == RepeatMode.QUEUE) 0
        else null
    }

    /**
     * Resolves a "previous" press: restart the current track when [positionSeconds] is past the
     * threshold, otherwise step back (wrapping under QUEUE). Returns the target index and whether
     * it should be treated as a restart of the same track.
     */
    fun previousTarget(
        size: Int,
        index: Int,
        positionSeconds: Double,
        repeat: RepeatMode,
    ): Int? {
        if (size <= 0) return null
        if (positionSeconds > PREVIOUS_RESTART_THRESHOLD_SECONDS) return index
        return when {
            index - 1 >= 0 -> index - 1
            repeat == RepeatMode.QUEUE -> size - 1
            else -> index // already at first track: restart it
        }
    }
}
