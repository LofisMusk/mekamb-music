package pl.mekamb.music.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.Dp
import coil3.compose.AsyncImage
import coil3.network.NetworkHeaders
import coil3.network.httpHeaders
import coil3.request.ImageRequest
import coil3.request.crossfade
import kotlin.math.abs

/** Deterministic hue derived from any seed string, so the same track/album always gets the same
 * placeholder gradient — mirroring the design prototype's `oklch(hue)` placeholder art (there is no
 * per-track color from the backend; this is only a stand-in shown until real artwork loads, or
 * permanently for tracks with no embedded art). */
private fun seedHue(seed: String): Float = (abs(seed.hashCode()) % 360).toFloat()

fun gradientForSeed(seed: String): Brush {
    val hue = seedHue(seed)
    val hue2 = (hue + 45f) % 360f
    return Brush.linearGradient(
        listOf(Color.hsv(hue, 0.55f, 0.62f), Color.hsv(hue2, 0.55f, 0.26f)),
    )
}

/**
 * Square/circular artwork tile. A gradient placeholder (keyed off [seed]) is always drawn first;
 * the real image from `GET /tracks/{id}/artwork` is layered on top via Coil once it loads, and
 * simply never appears if the request 404s/fails (no error state needed — the gradient IS the
 * fallback).
 */
@Composable
fun ArtworkImage(
    trackId: String?,
    endpoint: String,
    token: String,
    size: Dp,
    modifier: Modifier = Modifier,
    shape: Shape = RoundedCornerShape(8.dp),
    seed: String = trackId ?: "?",
) {
    Box(
        modifier
            .size(size)
            .clip(shape)
            .background(gradientForSeed(seed)),
    ) {
        if (trackId != null && endpoint.isNotBlank()) {
            val context = LocalContext.current
            val request = remember(trackId, endpoint, token) {
                ImageRequest.Builder(context)
                    .data("$endpoint/tracks/$trackId/artwork")
                    .httpHeaders(NetworkHeaders.Builder().set("Authorization", "Bearer $token").build())
                    .crossfade(150)
                    .build()
            }
            AsyncImage(
                model = request,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.size(size),
            )
        }
    }
}

@Composable
fun CircularArtworkImage(
    trackId: String?,
    endpoint: String,
    token: String,
    size: Dp,
    modifier: Modifier = Modifier,
    seed: String = trackId ?: "?",
) = ArtworkImage(trackId, endpoint, token, size, modifier, CircleShape, seed)

/** Solid gradient tile with no backing image at all — for artist/mix/liked hero art that's
 * entirely client-generated (there's no artist-portrait or mix-art endpoint on the backend). */
@Composable
fun GradientTile(seed: String, size: Dp, modifier: Modifier = Modifier, shape: Shape = RoundedCornerShape(8.dp)) {
    Box(modifier.size(size).clip(shape).background(gradientForSeed(seed)))
}

/** Vertical "hero" wash fading into the background, matching the design's
 * `linear-gradient(180deg, oklch(hue) 0%, rgba(11,11,13,0) 100%)` album/artist/mix headers. */
fun heroBrushForSeed(seed: String, baseColor: Color): Brush {
    val hue = seedHue(seed)
    return Brush.verticalGradient(listOf(Color.hsv(hue, 0.45f, 0.4f), baseColor))
}
