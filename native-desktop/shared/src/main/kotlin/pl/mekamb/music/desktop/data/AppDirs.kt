package pl.mekamb.music.desktop.data

import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption

/** Per-OS application directories, created lazily on first access. */
object AppDirs {

    val configDir: Path by lazy { ensure(rawConfigDir()) }
    val dataDir: Path by lazy { ensure(rawDataDir()) }
    val cacheDir: Path by lazy { ensure(rawCacheDir()) }

    private enum class Os { MAC, WINDOWS, LINUX }

    private val os: Os by lazy {
        val name = System.getProperty("os.name").orEmpty().lowercase()
        when {
            name.contains("mac") || name.contains("darwin") -> Os.MAC
            name.contains("win") -> Os.WINDOWS
            else -> Os.LINUX
        }
    }

    private val home: Path get() = Path.of(System.getProperty("user.home"))

    private fun env(name: String): Path? =
        System.getenv(name)?.takeIf { it.isNotBlank() }?.let { Path.of(it) }

    private fun rawConfigDir(): Path = when (os) {
        Os.MAC -> home.resolve("Library/Application Support/MekambMusic")
        Os.WINDOWS -> (env("APPDATA") ?: home.resolve("AppData/Roaming")).resolve("MekambMusic")
        Os.LINUX -> (env("XDG_CONFIG_HOME") ?: home.resolve(".config")).resolve("mekamb-music")
    }

    private fun rawDataDir(): Path = when (os) {
        Os.MAC -> home.resolve("Library/Application Support/MekambMusic")
        Os.WINDOWS -> (env("APPDATA") ?: home.resolve("AppData/Roaming")).resolve("MekambMusic")
        Os.LINUX -> (env("XDG_DATA_HOME") ?: home.resolve(".local/share")).resolve("mekamb-music")
    }

    private fun rawCacheDir(): Path = when (os) {
        Os.MAC -> home.resolve("Library/Caches/MekambMusic")
        Os.WINDOWS -> (env("LOCALAPPDATA") ?: home.resolve("AppData/Local")).resolve("MekambMusic/cache")
        Os.LINUX -> (env("XDG_CACHE_HOME") ?: home.resolve(".cache")).resolve("mekamb-music")
    }

    private fun ensure(path: Path): Path {
        Files.createDirectories(path)
        return path
    }
}

/** Moves [source] over [target], atomically when the filesystem supports it. */
internal fun atomicReplace(source: Path, target: Path) {
    try {
        Files.move(source, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
    } catch (unsupported: AtomicMoveNotSupportedException) {
        Files.move(source, target, StandardCopyOption.REPLACE_EXISTING)
    }
}
