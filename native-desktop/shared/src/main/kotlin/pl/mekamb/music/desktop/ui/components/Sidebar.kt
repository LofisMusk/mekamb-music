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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Album
import androidx.compose.material.icons.filled.CloudDownload
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.LibraryMusic
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.QueueMusic
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.BuildInfo
import pl.mekamb.music.desktop.api.PlaylistSummary
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.vm.Screen

private data class NavEntry(val label: String, val icon: ImageVector, val screen: Screen)

private val TOP_NAV = listOf(
    NavEntry("Home", Icons.Filled.Home, Screen.Home),
    NavEntry("Library", Icons.Filled.LibraryMusic, Screen.Library),
    NavEntry("Albums", Icons.Filled.Album, Screen.Albums),
    NavEntry("Liked", Icons.Filled.Favorite, Screen.Liked),
    NavEntry("Playlists", Icons.Filled.QueueMusic, Screen.Playlists),
)

private val SOURCE_NAV = listOf(
    NavEntry("Torrent Search", Icons.Filled.Search, Screen.TorrentSearch),
    NavEntry("Indexer Search", Icons.Filled.Dns, Screen.IndexerSearch),
    NavEntry("Imports", Icons.Filled.CloudDownload, Screen.Imports),
)

private val SIDEBAR_WIDTH = 240.dp
private val SIDEBAR_COMPACT_WIDTH = 72.dp

/**
 * Left navigation column: branding, primary nav, playlists, settings. In [compact] mode
 * (narrow windows) it collapses to an icon-only rail — the playlist list and inline creation
 * are dropped there since there isn't room to show them usefully; the Playlists screen itself
 * still has full create/list/rename/delete.
 */
@Composable
fun Sidebar(compact: Boolean = false) {
    val app = LocalApp.current
    val currentScreen = app.navigation.collectAsState().value
    val playlists = app.playlists.collectAsState().value
    var showCreateDialog by remember { mutableStateOf(false) }
    // Scoped to Sidebar (which lives for the app's lifetime), not to the dialog itself —
    // the dialog is removed from composition (and its own scope cancelled) as soon as
    // onDismiss() runs, which happens before the create+refresh network calls finish.
    val scope = rememberCoroutineScope()

    Surface(
        modifier = Modifier.width(if (compact) SIDEBAR_COMPACT_WIDTH else SIDEBAR_WIDTH).fillMaxHeight(),
        color = MekambColors.Surface,
    ) {
        // Scrollable rather than height-weighted: on short windows a weight(1f) section here
        // would get squeezed toward zero and hide the playlist list instead of scrolling to it.
        Column(
            modifier = Modifier.fillMaxHeight().verticalScroll(rememberScrollState()).padding(vertical = 16.dp),
        ) {
            if (compact) {
                Icon(
                    imageVector = Icons.Filled.MusicNote,
                    contentDescription = "Mekamb Music",
                    tint = MekambColors.Accent,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
                )
            } else {
                Column(modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
                    Text(
                        text = "Mekamb Music",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = MekambColors.Accent,
                    )
                    Text(
                        text = "v${BuildInfo.APP_VERSION}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MekambColors.Muted,
                    )
                }
            }

            Column(modifier = Modifier.padding(top = 16.dp)) {
                TOP_NAV.forEach { entry ->
                    NavRow(entry, isSelected(currentScreen, entry.screen), compact) { app.navigate(entry.screen) }
                }
            }

            HorizontalDivider(color = MekambColors.Stroke, modifier = Modifier.padding(vertical = 12.dp))

            Column {
                SOURCE_NAV.forEach { entry ->
                    NavRow(entry, isSelected(currentScreen, entry.screen), compact) { app.navigate(entry.screen) }
                }
            }

            if (!compact) {
                HorizontalDivider(color = MekambColors.Stroke, modifier = Modifier.padding(vertical = 12.dp))

                Text(
                    text = "PLAYLISTS",
                    style = MaterialTheme.typography.labelSmall,
                    color = MekambColors.Muted,
                    letterSpacing = 1.2.sp,
                    modifier = Modifier.padding(start = 20.dp, end = 20.dp, bottom = 4.dp),
                )

                Column {
                    playlists.forEach { playlist ->
                        PlaylistRow(
                            playlist = playlist,
                            isSelected = currentScreen is Screen.PlaylistDetail && currentScreen.playlistId == playlist.id,
                            onClick = { app.navigate(Screen.PlaylistDetail(playlist.id)) },
                        )
                    }
                }

                TextButton(
                    onClick = { showCreateDialog = true },
                    modifier = Modifier.padding(start = 12.dp, end = 12.dp, top = 4.dp),
                ) {
                    Text("+ New playlist", color = MekambColors.Accent)
                }
            }

            HorizontalDivider(color = MekambColors.Stroke, modifier = Modifier.padding(vertical = 12.dp))

            NavRow(
                NavEntry("Settings", Icons.Filled.Settings, Screen.Settings),
                isSelected(currentScreen, Screen.Settings),
                compact,
            ) { app.navigate(Screen.Settings) }
        }
    }

    if (showCreateDialog) {
        CreatePlaylistDialog(scope = scope, onDismiss = { showCreateDialog = false })
    }
}

private fun isSelected(current: Screen, target: Screen): Boolean = current == target

@Composable
private fun NavRow(entry: NavEntry, selected: Boolean, compact: Boolean = false, onClick: () -> Unit) {
    val interactionSource = remember { MutableInteractionSource() }
    val isHovered by interactionSource.collectIsHoveredAsState()
    val background = when {
        selected -> MekambColors.Chip
        isHovered -> MekambColors.Elevated
        else -> Color.Transparent
    }
    val tint = if (selected) MekambColors.Accent else MekambColors.Muted
    val textColor = if (selected) MekambColors.Accent else MekambColors.Text

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 2.dp)
            .clip(RoundedCornerShape(8.dp))
            .hoverable(interactionSource)
            .clickable(interactionSource = interactionSource, indication = null, onClick = onClick)
            .background(background)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(imageVector = entry.icon, contentDescription = entry.label, tint = tint)
        if (!compact) {
            Text(text = entry.label, color = textColor, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun PlaylistRow(playlist: PlaylistSummary, isSelected: Boolean, onClick: () -> Unit) {
    val interactionSource = remember { MutableInteractionSource() }
    val isHovered by interactionSource.collectIsHoveredAsState()
    val background = when {
        isSelected -> MekambColors.Chip
        isHovered -> MekambColors.Elevated
        else -> Color.Transparent
    }
    val textColor = if (isSelected) MekambColors.Accent else MekambColors.Text

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 1.dp)
            .clip(RoundedCornerShape(8.dp))
            .hoverable(interactionSource)
            .clickable(interactionSource = interactionSource, indication = null, onClick = onClick)
            .background(background)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(
            imageVector = Icons.Filled.MusicNote,
            contentDescription = null,
            tint = MekambColors.Muted,
            modifier = Modifier.padding(0.dp),
        )
        Text(
            text = playlist.name,
            color = textColor,
            style = MaterialTheme.typography.bodyMedium,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun CreatePlaylistDialog(scope: CoroutineScope, onDismiss: () -> Unit) {
    val app = LocalApp.current
    var name by remember { mutableStateOf("") }

    Dialog(onDismissRequest = onDismiss) {
        Surface(color = MekambColors.Elevated, shape = RoundedCornerShape(12.dp)) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    text = "New playlist",
                    style = MaterialTheme.typography.titleMedium,
                    color = MekambColors.Text,
                )
                TextField(
                    value = name,
                    onValueChange = { name = it },
                    singleLine = true,
                    placeholder = { Text("Playlist name", color = MekambColors.Muted) },
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = MekambColors.Chip,
                        unfocusedContainerColor = MekambColors.Chip,
                        focusedTextColor = MekambColors.Text,
                        unfocusedTextColor = MekambColors.Text,
                        cursorColor = MekambColors.Accent,
                    ),
                    modifier = Modifier.padding(top = 12.dp).fillMaxWidth(),
                )
                Row(
                    modifier = Modifier.padding(top = 16.dp).fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                    TextButton(
                        onClick = {
                            val trimmed = name.trim()
                            if (trimmed.isNotEmpty()) {
                                scope.launch {
                                    app.api.createPlaylist(trimmed)
                                    app.refreshLibrary()
                                }
                            }
                            onDismiss()
                        },
                    ) {
                        Text("Create", color = MekambColors.Accent)
                    }
                }
            }
        }
    }
}
