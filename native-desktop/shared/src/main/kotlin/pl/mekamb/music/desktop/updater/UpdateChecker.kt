package pl.mekamb.music.desktop.updater

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.prepareGet
import io.ktor.client.statement.bodyAsChannel
import io.ktor.client.statement.bodyAsText
import io.ktor.http.HttpHeaders
import io.ktor.http.isSuccess
import io.ktor.utils.io.readAvailable
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import pl.mekamb.music.desktop.BuildInfo
import pl.mekamb.music.desktop.api.GhAsset
import pl.mekamb.music.desktop.api.GhRelease
import pl.mekamb.music.desktop.api.apiJson

data class AvailableUpdate(
    val version: String,
    val tagName: String,
    val notes: String?,
    val asset: GhAsset,
    val checksumsAsset: GhAsset?,
)

class UpdateVerificationException(message: String) : Exception(message)

// Desktop release tags look like v1.2.3 or v1.2.3-beta.1; the repo also carries
// android-* and ios-* tags that must never be offered to the desktop app.
private val DESKTOP_RELEASE_TAG = Regex("""^v\d+\.\d+\.\d+(-[0-9A-Za-z\-]+(?:\.[0-9A-Za-z\-]+)*)?$""")

/**
 * Pure release-selection logic, separated from networking for unit tests.
 * Returns the newest non-draft desktop release strictly newer than [currentVersion],
 * or null when there is none (or when [currentVersion] is unparseable).
 */
internal fun selectNewerRelease(releases: List<GhRelease>, currentVersion: String): GhRelease? {
    val current = SemVer.parse(currentVersion) ?: return null
    return releases.asSequence()
        .filter { !it.draft && DESKTOP_RELEASE_TAG.matches(it.tagName) }
        .mapNotNull { release -> SemVer.parse(release.tagName)?.let { it to release } }
        .maxByOrNull { it.first }
        ?.takeIf { it.first > current }
        ?.second
}

class UpdateChecker(private val httpClient: HttpClient) {

    suspend fun checkForUpdate(currentVersion: String): AvailableUpdate? {
        val response = httpClient.get(
            "https://api.github.com/repos/${BuildInfo.GITHUB_REPO}/releases?per_page=30",
        ) {
            header(HttpHeaders.Accept, "application/vnd.github+json")
        }
        if (!response.status.isSuccess()) return null
        val releases = apiJson.decodeFromString<List<GhRelease>>(response.bodyAsText())
        val release = selectNewerRelease(releases, currentVersion) ?: return null
        val asset = PlatformAssets.pickAsset(release.assets) ?: return null
        return AvailableUpdate(
            version = release.tagName.removePrefix("v"),
            tagName = release.tagName,
            notes = release.body,
            asset = asset,
            checksumsAsset = release.assets.find { it.name == "SHA256SUMS.txt" },
        )
    }

    /**
     * Streams the release asset into [targetDir]/<asset name> via a temp file + atomic move.
     * When the release ships a SHA256SUMS.txt, the download is verified against it.
     */
    suspend fun downloadUpdate(
        update: AvailableUpdate,
        targetDir: Path,
        onProgress: (Float) -> Unit,
    ): Path {
        Files.createDirectories(targetDir)
        val target = targetDir.resolve(update.asset.name)
        val temp = Files.createTempFile(targetDir, update.asset.name, ".part")
        val digest = MessageDigest.getInstance("SHA-256")
        try {
            httpClient.prepareGet(update.asset.browserDownloadUrl).execute { response ->
                if (!response.status.isSuccess()) {
                    throw UpdateVerificationException(
                        "Update download failed: HTTP ${response.status.value}",
                    )
                }
                val totalBytes = update.asset.size.takeIf { it > 0 }
                val channel = response.bodyAsChannel()
                var written = 0L
                Files.newOutputStream(temp).use { out ->
                    val buffer = ByteArray(DOWNLOAD_BUFFER_SIZE)
                    while (true) {
                        val read = channel.readAvailable(buffer, 0, buffer.size)
                        if (read == -1) break
                        if (read > 0) {
                            out.write(buffer, 0, read)
                            digest.update(buffer, 0, read)
                            written += read
                            totalBytes?.let {
                                onProgress((written.toDouble() / it).toFloat().coerceIn(0f, 1f))
                            }
                        }
                    }
                }
            }
            update.checksumsAsset?.let { checksums ->
                verifyChecksum(checksums, update.asset.name, digest.digest())
            }
            try {
                Files.move(
                    temp,
                    target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING,
                )
            } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
                Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING)
            }
            onProgress(1f)
            return target
        } finally {
            Files.deleteIfExists(temp)
        }
    }

    private suspend fun verifyChecksum(
        checksumsAsset: GhAsset,
        assetName: String,
        actualDigest: ByteArray,
    ) {
        val response = httpClient.get(checksumsAsset.browserDownloadUrl)
        if (!response.status.isSuccess()) return // checksum file unavailable — skip verification
        val expected = parseChecksumFor(response.bodyAsText(), assetName) ?: return
        val actual = actualDigest.joinToString("") { "%02x".format(it) }
        if (!actual.equals(expected, ignoreCase = true)) {
            throw UpdateVerificationException(
                "SHA-256 mismatch for $assetName: expected $expected, got $actual",
            )
        }
    }

    companion object {
        private const val DOWNLOAD_BUFFER_SIZE = 64 * 1024

        /** Finds the hex digest for [assetName] in standard `sha256sum` output. */
        internal fun parseChecksumFor(checksumsText: String, assetName: String): String? =
            checksumsText.lineSequence()
                .map { it.trim() }
                .mapNotNull { line ->
                    val parts = line.split(Regex("""\s+"""), limit = 2)
                    if (parts.size != 2) return@mapNotNull null
                    val name = parts[1].removePrefix("*").trim()
                    if (name == assetName) parts[0] else null
                }
                .firstOrNull()
    }
}
