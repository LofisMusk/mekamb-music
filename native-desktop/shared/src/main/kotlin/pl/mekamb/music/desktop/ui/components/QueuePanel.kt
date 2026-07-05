package pl.mekamb.music.desktop.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsHoveredAsState
import androidx.compose.foundation.hoverable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import pl.mekamb.music.desktop.api.Track
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.theme.MekambColors

/** Right-hand "Now Playing" / "Up Next" panel. */
@Composable
fun QueuePanel() {
    val app = LocalApp.current
    val player = app.player
    val currentTrack = player.currentTrack.collectAsState().value
    val queue = player.queue.collectAsState().value
    val currentIndex = player.currentIndex.collectAsState().value
    val upcoming = if (currentIndex in queue.indices) queue.drop(currentIndex + 1) else emptyList()

    Surface(
        modifier = Modifier.width(260.dp).fillMaxHeight(),
        color = MekambColors.Surface,
    ) {
        Column(modifier = Modifier.fillMaxHeight().padding(vertical = 16.dp)) {
            Text(
                text = "Now Playing",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MekambColors.Text,
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 8.dp),
            )
            if (currentTrack != null) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    ArtworkImage(trackId = currentTrack.id, size = 48.dp)
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = currentTrack.title,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MekambColors.Text,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        currentTrack.artist?.let {
                            Text(
                                text = it,
                                style = MaterialTheme.typography.bodySmall,
                                color = MekambColors.Muted,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                }
            } else {
                EmptyState(title = "Nothing playing", subtitle = "Pick a track to get started")
            }

            HorizontalDivider(color = MekambColors.Stroke, modifier = Modifier.padding(vertical = 16.dp))

            Text(
                text = "Up Next",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MekambColors.Text,
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 8.dp),
            )

            LazyColumn(modifier = Modifier.weight(1f)) {
                itemsIndexed(upcoming) { relativeIndex, track ->
                    val absoluteIndex = currentIndex + 1 + relativeIndex
                    UpNextRow(
                        track = track,
                        onClick = { player.jumpTo(absoluteIndex) },
                        onRemove = { player.removeFromQueue(absoluteIndex) },
                    )
                }
            }

            TextButton(
                onClick = { player.clearUpcoming() },
                enabled = upcoming.isNotEmpty(),
                modifier = Modifier.padding(horizontal = 8.dp),
            ) {
                Text(
                    text = "Clear upcoming",
                    color = if (upcoming.isNotEmpty()) MekambColors.Accent else MekambColors.Muted,
                )
            }
        }
    }
}

@Composable
private fun UpNextRow(track: Track, onClick: () -> Unit, onRemove: () -> Unit) {
    val interactionSource = remember { MutableInteractionSource() }
    val isHovered by interactionSource.collectIsHoveredAsState()

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .hoverable(interactionSource)
            .clickable(interactionSource = interactionSource, indication = null, onClick = onClick)
            .background(if (isHovered) MekambColors.Elevated else Color.Transparent)
            .padding(horizontal = 16.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        ArtworkImage(trackId = track.id, size = 32.dp, cornerRadius = 6.dp)
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = track.title,
                style = MaterialTheme.typography.bodySmall,
                color = MekambColors.Text,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            track.artist?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.labelSmall,
                    color = MekambColors.Muted,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        IconButton(onClick = onRemove, modifier = Modifier.width(28.dp)) {
            Icon(
                imageVector = Icons.Filled.Close,
                contentDescription = "Remove from queue",
                tint = MekambColors.Muted,
                modifier = Modifier.width(16.dp),
            )
        }
    }
}
