package pl.mekamb.music

import android.app.Application
import coil3.ImageLoader
import coil3.PlatformContext
import coil3.SingletonImageLoader
import coil3.network.okhttp.OkHttpNetworkFetcherFactory

/**
 * Application entry point. Initializes the process-scoped [Playback] engine once (it was
 * previously initialized from `MainActivity.onCreate`, which works just as well, but doing it here
 * makes it independent of any particular Activity existing) and supplies the single Coil
 * [ImageLoader] used by every `AsyncImage` in the Compose UI.
 */
class MekambApp : Application(), SingletonImageLoader.Factory {
    override fun onCreate() {
        super.onCreate()
        Playback.init(this)
    }

    override fun newImageLoader(context: PlatformContext): ImageLoader {
        // Artwork requests need a Bearer token, which we attach per-request (see
        // ui/components/Artwork.kt) rather than through a shared OkHttp interceptor, since the
        // token can change (login/logout) during the process lifetime.
        return ImageLoader.Builder(context)
            .components { add(OkHttpNetworkFetcherFactory()) }
            .build()
    }
}
