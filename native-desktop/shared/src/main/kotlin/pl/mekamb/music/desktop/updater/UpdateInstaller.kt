package pl.mekamb.music.desktop.updater

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.attribute.PosixFilePermissions
import kotlin.system.exitProcess

/**
 * Hands the downloaded update artifact to the OS. On Windows and for Linux
 * AppImage self-replacement this call does not return — the process exits so
 * the installer / new binary can take over.
 */
object UpdateInstaller {

    fun install(file: Path): Result<String> = runCatching {
        val osName = System.getProperty("os.name").lowercase()
        val absolute = file.toAbsolutePath().toString()
        when {
            osName.contains("mac") || osName.contains("darwin") -> {
                ProcessBuilder("open", absolute).start()
                "The DMG has been opened — drag Mekamb Music to Applications, " +
                    "replace the old version, then relaunch. " +
                    "Unsigned app: right-click → Open on first launch."
            }

            osName.contains("win") -> {
                ProcessBuilder("msiexec", "/i", absolute).start()
                exitProcess(0)
            }

            else -> {
                val appImagePath = System.getenv("APPIMAGE")
                if (appImagePath != null && file.fileName.toString().endsWith(".AppImage")) {
                    Files.setPosixFilePermissions(
                        file,
                        PosixFilePermissions.fromString("rwxr-xr-x"),
                    )
                    val target = Path.of(appImagePath)
                    Files.move(
                        file,
                        target,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING,
                    )
                    ProcessBuilder(target.toAbsolutePath().toString()).start()
                    exitProcess(0)
                } else {
                    ProcessBuilder("xdg-open", absolute).start()
                    "The package has been opened with your system installer. " +
                        "If nothing happens, install it manually: " +
                        "sudo apt install ./${file.fileName}"
                }
            }
        }
    }
}
