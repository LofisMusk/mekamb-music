package pl.mekamb.music.desktop.data

import coil3.ImageLoader
import coil3.PlatformContext
import coil3.disk.DiskCache
import coil3.memory.MemoryCache
import coil3.network.ktor3.KtorNetworkFetcherFactory
import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.DefaultRequest
import io.ktor.client.request.header
import io.ktor.http.HttpHeaders
import okio.Path.Companion.toOkioPath

/**
 * Builds a Coil image loader for track artwork. Artwork endpoints require the bearer token,
 * so a dedicated Ktor client injects the Authorization header lazily (per request) — the token
 * is read from [tokenProvider] each time so it stays correct after settings changes.
 */
fun buildArtworkImageLoader(tokenProvider: () -> String): ImageLoader {
    val artworkClient = HttpClient(CIO) {
        install(DefaultRequest) {
            header(HttpHeaders.Authorization, "Bearer ${tokenProvider()}")
        }
    }
    return ImageLoader.Builder(PlatformContext.INSTANCE)
        .components {
            add(KtorNetworkFetcherFactory(httpClient = { artworkClient }))
        }
        .memoryCache {
            MemoryCache.Builder()
                .maxSizeBytes(64L * 1024 * 1024)
                .build()
        }
        .diskCache {
            DiskCache.Builder()
                .directory(AppDirs.cacheDir.resolve("artwork").toOkioPath())
                .maxSizeBytes(256L * 1024 * 1024)
                .build()
        }
        .build()
}
