package pl.mekamb.music.desktop.ui.components

import androidx.compose.foundation.ContextMenuArea
import androidx.compose.foundation.ContextMenuItem
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.hoverable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsHoveredAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.api.Track
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.util.formatDuration

/**
 * A single track list row: artwork, title/subtitle, duration, like toggle, and a "more options"
 * menu. Clicking anywhere on the row (outside the like/menu controls) starts playback of
 * [contextTracks] from [index]. Supports both a click-triggered dropdown and desktop right-click.
 */
@Composable
fun TrackRow(
    track: Track,
    contextTracks: List<Track>,
    index: Int,
    showArt: Boolean = true,
    trailing: (@Composable () -> Unit)? = null,
) {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()
    val interactionSource = remember { MutableInteractionSource() }
    val isHovered by interactionSource.collectIsHoveredAsState()
    val isLiked = app.likedTrackIds.collectAsState().value.contains(track.id)
    var showMenu by remember { mutableStateOf(false) }
    var showDeleteConfirm by remember { mutableStateOf(false) }

    val subtitle = listOfNotNull(track.artist, track.album).joinToString(" · ").ifBlank { null }

    val contextMenuItems = {
        listOf(
            ContextMenuItem("Play") { app.player.playTracks(listOf(track)) },
            ContextMenuItem("Play next") { app.player.playNextInQueue(track) },
            ContextMenuItem("Add to queue") { app.player.addToQueue(track) },
            ContextMenuItem(if (isLiked) "Unlike" else "Like") { app.toggleLike(track) },
            ContextMenuItem("Delete from library") { showDeleteConfirm = true },
        )
    }

    ContextMenuArea(items = contextMenuItems) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .background(if (isHovered) MekambColors.Elevated else Color.Transparent)
                .hoverable(interactionSource)
                .clickable(interactionSource = interactionSource, indication = null) {
                    app.player.playTracks(contextTracks, index)
                }
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (showArt) {
                ArtworkImage(trackId = track.id, size = 44.dp)
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = track.title,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MekambColors.Text,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                if (subtitle != null) {
                    Text(
                        text = subtitle,
                        style = MaterialTheme.typography.bodySmall,
                        color = MekambColors.Muted,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            trailing?.invoke()
            Text(
                text = formatDuration(track.durationSeconds),
                style = MaterialTheme.typography.bodySmall,
                color = MekambColors.Muted,
            )
            IconButton(onClick = { app.toggleLike(track) }) {
                Icon(
                    imageVector = if (isLiked) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                    contentDescription = if (isLiked) "Unlike" else "Like",
                    tint = if (isLiked) MekambColors.LikedPink else MekambColors.Muted,
                )
            }
            Box {
                IconButton(onClick = { showMenu = true }) {
                    Icon(
                        imageVector = Icons.Filled.MoreVert,
                        contentDescription = "More options",
                        tint = MekambColors.Muted,
                    )
                }
                DropdownMenu(expanded = showMenu, onDismissRequest = { showMenu = false }) {
                    TrackContextMenuItems(
                        track = track,
                        onDismiss = { showMenu = false },
                        onRequestDelete = { showDeleteConfirm = true },
                    )
                }
            }
        }
    }

    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            title = { Text("Delete from library?") },
            text = { Text("\"${track.title}\" will be permanently removed from your library.") },
            confirmButton = {
                TextButton(onClick = {
                    scope.launch {
                        app.api.deleteTrack(track.id)
                        app.refreshLibrary()
                    }
                    showDeleteConfirm = false
                }) {
                    Text("Delete", color = MekambColors.Danger)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) { Text("Cancel") }
            },
        )
    }
}
