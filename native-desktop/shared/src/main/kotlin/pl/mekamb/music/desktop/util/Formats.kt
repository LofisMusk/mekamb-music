package pl.mekamb.music.desktop.util

import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Formats a duration in seconds as "3:45" or "1:02:03". Null/invalid input yields "0:00". */
fun formatDuration(seconds: Double?): String {
    val total = seconds?.takeIf { it.isFinite() && it > 0 }?.toLong() ?: return "0:00"
    val hours = total / 3600
    val minutes = (total % 3600) / 60
    val secs = total % 60
    return if (hours > 0) {
        String.format(Locale.ROOT, "%d:%02d:%02d", hours, minutes, secs)
    } else {
        String.format(Locale.ROOT, "%d:%02d", minutes, secs)
    }
}

/** Formats a byte count as a human readable size, e.g. "1.2 GB". */
fun formatBytes(bytes: Long?): String {
    if (bytes == null || bytes < 0) return "0 B"
    if (bytes < 1024) return "$bytes B"
    val units = listOf("KB", "MB", "GB", "TB", "PB")
    var value = bytes.toDouble()
    var unitIndex = -1
    while (value >= 1024 && unitIndex < units.lastIndex) {
        value /= 1024
        unitIndex++
    }
    val pattern = if (value >= 100) "%.0f %s" else "%.1f %s"
    return String.format(Locale.ROOT, pattern, value, units[unitIndex])
}

/** Renders an ISO-ish backend timestamp as a short relative label ("5 min ago", "Mar 3"). */
fun formatRelativeDate(isoTimestamp: String?): String {
    val instant = parseInstantOrNull(isoTimestamp) ?: return ""
    val elapsed = Duration.between(instant, Instant.now())
    if (elapsed.isNegative) return "just now"
    return when {
        elapsed.toMinutes() < 1 -> "just now"
        elapsed.toMinutes() < 60 -> "${elapsed.toMinutes()} min ago"
        elapsed.toHours() < 24 -> "${elapsed.toHours()} h ago"
        elapsed.toDays() < 7 -> "${elapsed.toDays()} d ago"
        else -> {
            val date = instant.atZone(ZoneId.systemDefault()).toLocalDate()
            val pattern = if (date.year == LocalDate.now().year) "MMM d" else "MMM d, yyyy"
            date.format(DateTimeFormatter.ofPattern(pattern, Locale.ROOT))
        }
    }
}

// Backend timestamps arrive with or without zone info depending on endpoint; try both,
// treating zone-less values as UTC.
private fun parseInstantOrNull(raw: String?): Instant? {
    val text = raw?.trim().orEmpty()
    if (text.isEmpty()) return null
    return runCatching { Instant.parse(text) }.getOrNull()
        ?: runCatching { OffsetDateTime.parse(text).toInstant() }.getOrNull()
        ?: runCatching { LocalDateTime.parse(text).toInstant(ZoneOffset.UTC) }.getOrNull()
}
