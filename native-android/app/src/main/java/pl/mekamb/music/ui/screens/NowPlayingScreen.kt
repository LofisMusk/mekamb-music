package pl.mekamb.music.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.QueueMusic
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Repeat
import androidx.compose.material.icons.filled.RepeatOne
import androidx.compose.material.icons.filled.Shuffle
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.AppUiState
import pl.mekamb.music.RepeatMode
import pl.mekamb.music.data.PlaybackSnapshot
import pl.mekamb.music.ui.components.ArtworkImage
import pl.mekamb.music.ui.components.formatDuration
import pl.mekamb.music.ui.components.gradientForSeed
import pl.mekamb.music.ui.theme.MekambColors

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NowPlayingScreen(
    uiState: AppUiState,
    playback: PlaybackSnapshot,
    endpoint: String,
    token: String,
    onClose: () -> Unit,
    onTogglePlay: () -> Unit,
    onNext: () -> Unit,
    onPrevious: () -> Unit,
    onToggleShuffle: () -> Unit,
    onCycleRepeat: () -> Unit,
    onSeek: (Int) -> Unit,
    onToggleLike: () -> Unit,
    onPlayQueueIndex: (Int) -> Unit = {},
) {
    val track = playback.currentTrack ?: return
    var showQueue by remember { mutableStateOf(false) }
    val isLiked = uiState.likedTrackIds.contains(track.id)

    Box(
        Modifier
            .fillMaxSize()
            .background(gradientForSeed(track.id)),
    ) {
        Box(
            Modifier
                .fillMaxSize()
                .background(
                    androidx.compose.ui.graphics.Brush.verticalGradient(
                        listOf(Color(0x8C080A10), Color(0xE0080A10)),
                    ),
                ),
        )
        Column(Modifier.fillMaxSize().padding(horizontal = 24.dp).padding(top = 56.dp, bottom = 40.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(34.dp)
                        .background(Color.White.copy(alpha = 0.08f), RoundedCornerShape(10.dp))
                        .clickable(onClick = onClose),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Filled.ExpandMore, contentDescription = "Close", tint = Color.White.copy(alpha = 0.8f))
                }
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("PLAYING FROM ALBUM", color = Color.White.copy(alpha = 0.5f), fontSize = 9.5.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 1.3.sp)
                    Text(track.displayAlbum, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 2.dp))
                }
                Spacer(Modifier.size(34.dp))
            }
            Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                ArtworkImage(track.id, endpoint, token, size = 280.dp, shape = RoundedCornerShape(14.dp), seed = track.id)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(track.title, color = MekambColors.TextPrimary, fontSize = 20.sp, fontWeight = FontWeight.ExtraBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(track.displayArtist, color = MekambColors.Link, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 3.dp))
                }
                Icon(
                    if (isLiked) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                    contentDescription = "Like",
                    tint = if (isLiked) MekambColors.Like else Color.White,
                    modifier = Modifier.size(21.dp).clickable(onClick = onToggleLike),
                )
            }
            Spacer(Modifier.height(16.dp))
            var dragPosition by remember { mutableFloatStateOf(-1f) }
            val fraction = if (dragPosition >= 0f) dragPosition else if (playback.durationMs > 0) playback.positionMs.toFloat() / playback.durationMs.toFloat() else 0f
            Slider(
                value = fraction.coerceIn(0f, 1f),
                onValueChange = { dragPosition = it },
                onValueChangeFinished = {
                    if (dragPosition >= 0f && playback.durationMs > 0) onSeek((dragPosition * playback.durationMs).toInt())
                    dragPosition = -1f
                },
                colors = SliderDefaults.colors(thumbColor = Color.White, activeTrackColor = MekambColors.Accent, inactiveTrackColor = Color.White.copy(alpha = 0.14f)),
                modifier = Modifier.fillMaxWidth(),
            )
            Row(Modifier.fillMaxWidth()) {
                val shownMs = if (dragPosition >= 0f) (dragPosition * playback.durationMs).toInt() else playback.positionMs
                Text(formatDuration(shownMs / 1000.0), color = Color.White.copy(alpha = 0.55f), fontSize = 11.sp, modifier = Modifier.weight(1f))
                Text(formatDuration(playback.durationMs / 1000.0), color = Color.White.copy(alpha = 0.55f), fontSize = 11.sp)
            }
            Spacer(Modifier.height(10.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Filled.Shuffle,
                    contentDescription = "Shuffle",
                    tint = if (playback.shuffle) MekambColors.Accent else Color.White.copy(alpha = 0.55f),
                    modifier = Modifier.size(20.dp).clickable(onClick = onToggleShuffle),
                )
                Icon(Icons.Filled.SkipPrevious, contentDescription = "Previous", tint = Color.White, modifier = Modifier.size(30.dp).clickable(onClick = onPrevious))
                Box(
                    Modifier
                        .size(64.dp)
                        .background(MekambColors.Accent, CircleShape)
                        .clickable(onClick = onTogglePlay),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        if (playback.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                        contentDescription = if (playback.isPlaying) "Pause" else "Play",
                        tint = MekambColors.BackgroundAlt,
                        modifier = Modifier.size(28.dp),
                    )
                }
                Icon(Icons.Filled.SkipNext, contentDescription = "Next", tint = Color.White, modifier = Modifier.size(30.dp).clickable(onClick = onNext))
                Box {
                    Icon(
                        if (playback.repeatMode == RepeatMode.One) Icons.Filled.RepeatOne else Icons.Filled.Repeat,
                        contentDescription = "Repeat",
                        tint = if (playback.repeatMode != RepeatMode.Off) MekambColors.Accent else Color.White.copy(alpha = 0.55f),
                        modifier = Modifier.size(20.dp).clickable(onClick = onCycleRepeat),
                    )
                }
            }
            Spacer(Modifier.height(14.dp))
            val nextTrack = playback.nextTrack
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(Color.White.copy(alpha = 0.06f), RoundedCornerShape(10.dp))
                    .clickable { showQueue = true }
                    .padding(horizontal = 13.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("UP NEXT", color = Color.White.copy(alpha = 0.5f), fontSize = 9.5.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 1.sp)
                Text(
                    nextTrack?.let { "${it.title} — ${it.displayArtist}" } ?: "End of queue",
                    color = Color.White,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f).padding(start = 10.dp),
                )
                Icon(Icons.AutoMirrored.Filled.QueueMusic, contentDescription = "Queue", tint = Color.White.copy(alpha = 0.6f), modifier = Modifier.size(16.dp))
            }
        }
    }

    if (showQueue) {
        ModalBottomSheet(onDismissRequest = { showQueue = false }, containerColor = MekambColors.Surface) {
            Text("Up Next", color = MekambColors.TextPrimary, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp))
            LazyColumn(Modifier.fillMaxWidth().heightIn(max = 420.dp), contentPadding = PaddingValues(bottom = 24.dp)) {
                items(playback.queue.size, key = { index -> "${playback.queue[index].id}-$index" }) { index ->
                    val queueTrack = playback.queue[index]
                    val isCurrent = index == playback.currentIndex
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clickable { onPlayQueueIndex(index); showQueue = false }
                            .padding(horizontal = 18.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        ArtworkImage(queueTrack.id, endpoint, token, size = 42.dp, shape = RoundedCornerShape(6.dp))
                        Column(Modifier.weight(1f).padding(start = 11.dp)) {
                            Text(queueTrack.title, color = if (isCurrent) MekambColors.Accent else MekambColors.TextPrimary, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(queueTrack.displayArtist, color = MekambColors.TextMuted, fontSize = 11.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
        }
    }
}
