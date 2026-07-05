package pl.mekamb.music.desktop.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil3.compose.SubcomposeAsyncImage
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.theme.MekambColors

/**
 * Renders track artwork fetched through the shared Coil loader, falling back to a music-note
 * placeholder when there is no track id or the artwork fails to load.
 */
@Composable
fun ArtworkImage(trackId: String?, size: Dp, cornerRadius: Dp = 8.dp) {
    val app = LocalApp.current
    val shape = RoundedCornerShape(cornerRadius)
    if (trackId == null) {
        ArtworkPlaceholder(size = size, shape = shape)
        return
    }
    SubcomposeAsyncImage(
        model = app.api.artworkUrl(trackId),
        imageLoader = app.imageLoader,
        contentDescription = null,
        modifier = Modifier.size(size).clip(shape),
        loading = { ArtworkPlaceholder(size = size, shape = shape) },
        error = { ArtworkPlaceholder(size = size, shape = shape) },
    )
}

@Composable
private fun ArtworkPlaceholder(size: Dp, shape: RoundedCornerShape) {
    Box(
        modifier = Modifier.size(size).clip(shape).background(MekambColors.Elevated),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = Icons.Filled.MusicNote,
            contentDescription = null,
            tint = MekambColors.Muted,
            modifier = Modifier.size(size / 2),
        )
    }
}
