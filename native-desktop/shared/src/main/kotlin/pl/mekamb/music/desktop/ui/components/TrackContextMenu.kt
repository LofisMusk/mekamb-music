package pl.mekamb.music.desktop.ui.components

import androidx.compose.foundation.layout.Box
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.CloudDownload
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.PlaylistAdd
import androidx.compose.material.icons.filled.PlaylistPlay
import androidx.compose.material.icons.filled.QueueMusic
import androidx.compose.material.icons.filled.RemoveCircleOutline
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.api.Track
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.theme.MekambColors

/**
 * Shared context-menu contents for a single track, used both from [TrackRow]'s "more options"
 * dropdown and its right-click context menu. Deletion is intentionally deferred to the caller
 * (via [onRequestDelete]) since the confirmation dialog must survive dropdown dismissal.
 */
@Composable
fun TrackContextMenuItems(
    track: Track,
    onDismiss: () -> Unit,
    onRequestDelete: () -> Unit,
) {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()
    val isLiked = app.likedTrackIds.collectAsState().value.contains(track.id)
    val isOffline = app.downloads.offlineTrackIds.collectAsState().value.contains(track.id)
    var showPlaylistSubmenu by remember { mutableStateOf(false) }

    DropdownMenuItem(
        text = { Text("Play") },
        leadingIcon = { Icon(Icons.Filled.PlayArrow, contentDescription = null) },
        onClick = {
            app.player.playTracks(listOf(track))
            onDismiss()
        },
    )
    DropdownMenuItem(
        text = { Text("Play next") },
        leadingIcon = { Icon(Icons.Filled.PlaylistPlay, contentDescription = null) },
        onClick = {
            app.player.playNextInQueue(track)
            onDismiss()
        },
    )
    DropdownMenuItem(
        text = { Text("Add to queue") },
        leadingIcon = { Icon(Icons.Filled.QueueMusic, contentDescription = null) },
        onClick = {
            app.player.addToQueue(track)
            onDismiss()
        },
    )
    Box {
        DropdownMenuItem(
            text = { Text("Add to playlist") },
            leadingIcon = { Icon(Icons.Filled.PlaylistAdd, contentDescription = null) },
            trailingIcon = { Icon(Icons.Filled.ChevronRight, contentDescription = null) },
            onClick = { showPlaylistSubmenu = true },
        )
        val playlists = app.playlists.collectAsState().value
        DropdownMenu(expanded = showPlaylistSubmenu, onDismissRequest = { showPlaylistSubmenu = false }) {
            if (playlists.isEmpty()) {
                DropdownMenuItem(text = { Text("No playlists yet") }, onClick = {}, enabled = false)
            }
            playlists.forEach { playlist ->
                DropdownMenuItem(
                    text = { Text(playlist.name) },
                    onClick = {
                        scope.launch {
                            app.api.addTrackToPlaylist(playlist.id, track.id)
                            app.refreshLibrary()
                        }
                        showPlaylistSubmenu = false
                        onDismiss()
                    },
                )
            }
        }
    }
    DropdownMenuItem(
        text = { Text(if (isLiked) "Unlike" else "Like") },
        leadingIcon = {
            Icon(
                imageVector = if (isLiked) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                contentDescription = null,
                tint = if (isLiked) MekambColors.LikedPink else MekambColors.Muted,
            )
        },
        onClick = {
            app.toggleLike(track)
            onDismiss()
        },
    )
    DropdownMenuItem(
        text = { Text(if (isOffline) "Remove download" else "Download offline") },
        leadingIcon = {
            Icon(
                imageVector = if (isOffline) Icons.Filled.RemoveCircleOutline else Icons.Filled.CloudDownload,
                contentDescription = null,
            )
        },
        onClick = {
            if (isOffline) app.downloads.removeDownload(track.id) else app.downloads.downloadTrack(track)
            onDismiss()
        },
    )
    DropdownMenuItem(
        text = { Text("Delete from library") },
        leadingIcon = { Icon(Icons.Filled.Delete, contentDescription = null, tint = MekambColors.Danger) },
        onClick = {
            onRequestDelete()
            onDismiss()
        },
    )
}
