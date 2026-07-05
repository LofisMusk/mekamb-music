package pl.mekamb.music.desktop.updater

/**
 * Simplified semantic version. Pre-release versions sort below their release
 * (1.0.0-rc < 1.0.0); numeric pre-release identifiers compare numerically.
 */
data class SemVer(
    val major: Int,
    val minor: Int,
    val patch: Int,
    val preRelease: String? = null,
) : Comparable<SemVer> {

    override fun compareTo(other: SemVer): Int {
        if (major != other.major) return major.compareTo(other.major)
        if (minor != other.minor) return minor.compareTo(other.minor)
        if (patch != other.patch) return patch.compareTo(other.patch)
        val a = preRelease
        val b = other.preRelease
        return when {
            a == null && b == null -> 0
            a == null -> 1
            b == null -> -1
            else -> comparePreRelease(a, b)
        }
    }

    override fun toString(): String =
        "$major.$minor.$patch" + (preRelease?.let { "-$it" } ?: "")

    companion object {
        // Optional leading "v", three numeric parts, optional -prerelease, optional +build (ignored).
        private val PATTERN = Regex(
            """^[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z\-]+(?:\.[0-9A-Za-z\-]+)*))?(?:\+[0-9A-Za-z\-.]+)?$""",
        )

        fun parse(raw: String): SemVer? {
            val match = PATTERN.matchEntire(raw.trim()) ?: return null
            val (majorRaw, minorRaw, patchRaw, preRaw) = match.destructured
            val major = majorRaw.toIntOrNull() ?: return null
            val minor = minorRaw.toIntOrNull() ?: return null
            val patch = patchRaw.toIntOrNull() ?: return null
            return SemVer(major, minor, patch, preRaw.ifEmpty { null })
        }

        private fun comparePreRelease(a: String, b: String): Int {
            val aIds = a.split('.')
            val bIds = b.split('.')
            for (i in 0 until minOf(aIds.size, bIds.size)) {
                val x = aIds[i]
                val y = bIds[i]
                val xNum = x.toIntOrNull()
                val yNum = y.toIntOrNull()
                val cmp = when {
                    xNum != null && yNum != null -> xNum.compareTo(yNum)
                    xNum != null -> -1 // numeric identifiers sort below alphanumeric
                    yNum != null -> 1
                    else -> x.compareTo(y)
                }
                if (cmp != 0) return cmp
            }
            return aIds.size.compareTo(bIds.size)
        }
    }
}
