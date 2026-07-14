package pl.mekamb.music.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.AppUiState
import pl.mekamb.music.data.ApiTrack
import pl.mekamb.music.data.PlaybackSnapshot
import pl.mekamb.music.ui.components.ArtworkImage
import pl.mekamb.music.ui.components.BackIconButton
import pl.mekamb.music.ui.components.BigPlayButton
import pl.mekamb.music.ui.components.LikeButton
import pl.mekamb.music.ui.components.MixBadge
import pl.mekamb.music.ui.components.TrackRow
import pl.mekamb.music.ui.components.heroBrushForSeed
import pl.mekamb.music.ui.theme.MekambColors

@Composable
fun MixScreen(
    mixId: String,
    uiState: AppUiState,
    playback: PlaybackSnapshot,
    endpoint: String,
    token: String,
    onBack: () -> Unit,
    onPlay: (ApiTrack, List<ApiTrack>) -> Unit,
    onToggleLike: (ApiTrack) -> Unit,
) {
    val mix = uiState.dailyMixes.firstOrNull { it.id == mixId } ?: run {
        Column(Modifier.fillMaxSize().padding(18.dp)) {
            BackIconButton(onBack)
            Spacer(Modifier.height(24.dp))
            Text("This mix is no longer available.", color = MekambColors.TextMuted)
        }
        return
    }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
        item {
            Column(
                Modifier
                    .fillMaxWidth()
                    .background(heroBrushForSeed(mix.id, MekambColors.Background))
                    .padding(horizontal = 18.dp, vertical = 8.dp),
            ) {
                BackIconButton(onBack)
                Spacer(Modifier.height(14.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(88.dp).background(androidx.compose.ui.graphics.Brush.linearGradient(listOf(MekambColors.AccentDeep, MekambColors.Accent)), RoundedCornerShape(10.dp))) {
                        MixBadge(Modifier.padding(6.dp))
                    }
                    Column(Modifier.weight(1f).padding(start = 14.dp)) {
                        Text(mix.title, color = MekambColors.TextPrimary, fontSize = 22.sp, fontWeight = FontWeight.ExtraBold)
                        Text(mix.description, color = MekambColors.TextMuted, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 4.dp))
                        Text("${mix.tracks.size} tracks · ${mix.totalMinutes} min · refreshed daily", color = MekambColors.TextMuted, fontSize = 11.5.sp, modifier = Modifier.padding(top = 3.dp))
                    }
                    BigPlayButton(isPlaying = playback.isPlaying && mix.tracks.any { it.id == playback.currentTrack?.id }, size = 48.dp, onClick = {
                        mix.tracks.firstOrNull()?.let { onPlay(it, mix.tracks) }
                    })
                }
            }
        }
        items(mix.tracks, key = { it.id }) { track ->
            val isCurrent = playback.currentTrack?.id == track.id
            Box(Modifier.padding(horizontal = 18.dp)) {
                TrackRow(
                    title = track.title,
                    subtitle = "${track.displayArtist} · ${track.displayAlbum}",
                    isCurrent = isCurrent,
                    onClick = { onPlay(track, mix.tracks) },
                    leading = { ArtworkImage(track.id, endpoint, token, size = 46.dp, shape = RoundedCornerShape(6.dp)) },
                    trailing = { LikeButton(uiState.likedTrackIds.contains(track.id), onToggle = { onToggleLike(track) }) },
                )
            }
        }
    }
}
