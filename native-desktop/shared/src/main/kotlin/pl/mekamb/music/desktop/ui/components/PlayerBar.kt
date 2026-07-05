package pl.mekamb.music.desktop.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.QueueMusic
import androidx.compose.material.icons.filled.Repeat
import androidx.compose.material.icons.filled.RepeatOne
import androidx.compose.material.icons.filled.Shuffle
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlin.math.max
import pl.mekamb.music.desktop.player.RepeatMode
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.util.formatDuration

/** Bottom playback bar: current track, transport controls with seek, queue toggle, volume. */
@Composable
fun PlayerBar(queueVisible: Boolean, onToggleQueue: () -> Unit) {
    val app = LocalApp.current
    val player = app.player
    val currentTrack = player.currentTrack.collectAsState().value
    val isPlaying = player.isPlaying.collectAsState().value
    val shuffleEnabled = player.shuffleEnabled.collectAsState().value
    val repeatMode = player.repeatMode.collectAsState().value
    val positionSeconds = player.positionSeconds.collectAsState().value
    val durationSeconds = player.durationSeconds.collectAsState().value
    val volume = player.volume.collectAsState().value
    val isLiked = currentTrack?.let { app.likedTrackIds.collectAsState().value.contains(it.id) } ?: false

    var scrub by remember { mutableStateOf<Float?>(null) }

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .height(92.dp)
            .drawBehind {
                drawLine(
                    color = MekambColors.Stroke,
                    start = Offset(0f, 0f),
                    end = Offset(size.width, 0f),
                    strokeWidth = 1.dp.toPx(),
                )
            },
        color = MekambColors.Surface,
    ) {
        Row(
            modifier = Modifier.fillMaxHeight().padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // LEFT: current track info
            Row(
                modifier = Modifier.weight(0.28f),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                ArtworkImage(trackId = currentTrack?.id, size = 56.dp)
                Column(modifier = Modifier.weight(1f).padding(horizontal = 12.dp)) {
                    Text(
                        text = currentTrack?.title ?: "Nothing playing",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MekambColors.Text,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = currentTrack?.artist ?: "",
                        style = MaterialTheme.typography.bodySmall,
                        color = MekambColors.Muted,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                IconButton(
                    onClick = { currentTrack?.let { app.toggleLike(it) } },
                    enabled = currentTrack != null,
                ) {
                    Icon(
                        imageVector = if (isLiked) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                        contentDescription = if (isLiked) "Unlike" else "Like",
                        tint = if (isLiked) MekambColors.LikedPink else MekambColors.Muted,
                    )
                }
            }

            // CENTER: transport controls + seek bar
            Column(
                modifier = Modifier.weight(0.44f),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = { player.toggleShuffle() }) {
                        Icon(
                            imageVector = Icons.Filled.Shuffle,
                            contentDescription = "Shuffle",
                            tint = if (shuffleEnabled) MekambColors.Accent else MekambColors.Muted,
                        )
                    }
                    IconButton(onClick = { player.previous() }) {
                        Icon(
                            imageVector = Icons.Filled.SkipPrevious,
                            contentDescription = "Previous",
                            tint = MekambColors.Text,
                        )
                    }
                    IconButton(
                        onClick = { player.togglePlayPause() },
                        modifier = Modifier
                            .size(40.dp)
                            .clip(CircleShape)
                            .background(MekambColors.Accent),
                    ) {
                        Icon(
                            imageVector = if (isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                            contentDescription = if (isPlaying) "Pause" else "Play",
                            tint = MekambColors.BackgroundBottom,
                        )
                    }
                    IconButton(onClick = { player.next() }) {
                        Icon(
                            imageVector = Icons.Filled.SkipNext,
                            contentDescription = "Next",
                            tint = MekambColors.Text,
                        )
                    }
                    IconButton(onClick = { player.cycleRepeat() }) {
                        Icon(
                            imageVector = if (repeatMode == RepeatMode.TRACK) Icons.Filled.RepeatOne else Icons.Filled.Repeat,
                            contentDescription = "Repeat",
                            tint = if (repeatMode != RepeatMode.OFF) MekambColors.Accent else MekambColors.Muted,
                        )
                    }
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = formatDuration(scrub?.toDouble() ?: positionSeconds),
                        style = MaterialTheme.typography.labelSmall,
                        color = MekambColors.Muted,
                    )
                    val maxValue = max(durationSeconds?.toFloat() ?: 0f, 0.01f)
                    Slider(
                        value = (scrub ?: positionSeconds.toFloat()).coerceIn(0f, maxValue),
                        onValueChange = { scrub = it },
                        onValueChangeFinished = {
                            scrub?.let { player.seekTo(it.toDouble()) }
                            scrub = null
                        },
                        valueRange = 0f..maxValue,
                        colors = SliderDefaults.colors(
                            thumbColor = MekambColors.Accent,
                            activeTrackColor = MekambColors.Accent,
                            inactiveTrackColor = MekambColors.Chip,
                        ),
                        modifier = Modifier.weight(1f).padding(horizontal = 8.dp),
                    )
                    Text(
                        text = formatDuration(durationSeconds),
                        style = MaterialTheme.typography.labelSmall,
                        color = MekambColors.Muted,
                    )
                }
            }

            // RIGHT: queue toggle + volume, end-aligned
            Row(
                modifier = Modifier.weight(0.28f),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.End,
            ) {
                IconButton(onClick = onToggleQueue) {
                    Icon(
                        imageVector = Icons.Filled.QueueMusic,
                        contentDescription = "Toggle queue",
                        tint = if (queueVisible) MekambColors.Accent else MekambColors.Muted,
                    )
                }
                Icon(
                    imageVector = Icons.Filled.VolumeUp,
                    contentDescription = null,
                    tint = MekambColors.Muted,
                    modifier = Modifier.padding(horizontal = 4.dp),
                )
                Slider(
                    value = volume,
                    onValueChange = { player.setVolume(it) },
                    valueRange = 0f..1f,
                    colors = SliderDefaults.colors(
                        thumbColor = MekambColors.Accent,
                        activeTrackColor = MekambColors.Accent,
                        inactiveTrackColor = MekambColors.Chip,
                    ),
                    modifier = Modifier.width(120.dp),
                )
            }
        }
    }
}
