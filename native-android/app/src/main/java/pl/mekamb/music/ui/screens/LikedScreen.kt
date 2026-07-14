package pl.mekamb.music.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.roundToInt
import pl.mekamb.music.AppUiState
import pl.mekamb.music.data.ApiTrack
import pl.mekamb.music.data.PlaybackSnapshot
import pl.mekamb.music.ui.components.ArtworkImage
import pl.mekamb.music.ui.components.BackIconButton
import pl.mekamb.music.ui.components.BigPlayButton
import pl.mekamb.music.ui.components.LikeButton
import pl.mekamb.music.ui.components.TrackRow
import pl.mekamb.music.ui.theme.MekambColors

@Composable
fun LikedScreen(
    uiState: AppUiState,
    playback: PlaybackSnapshot,
    endpoint: String,
    token: String,
    onBack: () -> Unit,
    onPlay: (ApiTrack, List<ApiTrack>) -> Unit,
    onToggleLike: (ApiTrack) -> Unit,
) {
    val liked = uiState.likedTracks

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
        item {
            Column(
                Modifier
                    .fillMaxWidth()
                    .background(Brush.verticalGradient(listOf(MekambColors.AccentDeep.copy(alpha = 0.30f), MekambColors.BackgroundAlt.copy(alpha = 0f))))
                    .padding(horizontal = 18.dp, vertical = 8.dp),
            ) {
                BackIconButton(onBack)
                Spacer(Modifier.height(14.dp))
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    Box(
                        Modifier.size(88.dp).background(Brush.linearGradient(MekambColors.LikedHeroGradient), RoundedCornerShape(10.dp)),
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        Icon(Icons.Filled.Favorite, contentDescription = null, tint = Color.White, modifier = Modifier.size(34.dp))
                    }
                    Column(Modifier.weight(1f).padding(start = 14.dp)) {
                        Text("Liked Songs", color = MekambColors.TextPrimary, fontSize = 22.sp, fontWeight = FontWeight.ExtraBold)
                        val minutes = (liked.sumOf { it.durationSeconds ?: 0.0 } / 60.0).roundToInt()
                        Text("${liked.size} tracks · $minutes min", color = MekambColors.TextMuted, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
                    }
                    BigPlayButton(isPlaying = playback.isPlaying && liked.any { it.id == playback.currentTrack?.id }, size = 48.dp, onClick = {
                        liked.firstOrNull()?.let { onPlay(it, liked) }
                    })
                }
            }
        }
        if (liked.isEmpty()) {
            item {
                Text("Liked songs will show up here.", color = MekambColors.TextMuted, fontSize = 13.sp, modifier = Modifier.padding(18.dp))
            }
        }
        items(liked, key = { it.id }) { track ->
            val isCurrent = playback.currentTrack?.id == track.id
            Box(Modifier.padding(horizontal = 18.dp)) {
                TrackRow(
                    title = track.title,
                    subtitle = "${track.displayArtist} · ${track.displayAlbum}",
                    isCurrent = isCurrent,
                    onClick = { onPlay(track, liked) },
                    leading = { ArtworkImage(track.id, endpoint, token, size = 46.dp, shape = RoundedCornerShape(6.dp)) },
                    trailing = { LikeButton(true, onToggle = { onToggleLike(track) }) },
                )
            }
        }
    }
}
