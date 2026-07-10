package pl.mekamb.music.desktop.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import pl.mekamb.music.desktop.ui.components.ConnectionBanner
import pl.mekamb.music.desktop.ui.components.PlayerBar
import pl.mekamb.music.desktop.ui.components.QueuePanel
import pl.mekamb.music.desktop.ui.components.Sidebar
import pl.mekamb.music.desktop.ui.components.UpdateFlowHost
import pl.mekamb.music.desktop.ui.screens.AlbumDetailScreen
import pl.mekamb.music.desktop.ui.screens.AlbumsScreen
import pl.mekamb.music.desktop.ui.screens.HomeScreen
import pl.mekamb.music.desktop.ui.screens.CatalogScreen
import pl.mekamb.music.desktop.ui.screens.ImportsScreen
import pl.mekamb.music.desktop.ui.screens.LibrariesScreen
import pl.mekamb.music.desktop.ui.screens.LibraryDetailScreen
import pl.mekamb.music.desktop.ui.screens.LibraryScreen
import pl.mekamb.music.desktop.ui.screens.LikedScreen
import pl.mekamb.music.desktop.ui.screens.PlaylistDetailScreen
import pl.mekamb.music.desktop.ui.screens.PlaylistsScreen
import pl.mekamb.music.desktop.ui.screens.SettingsScreen
import pl.mekamb.music.desktop.vm.Screen

// Breakpoints below which fixed-width side panels would otherwise squeeze the main content
// area too small to use — collapse them instead of letting them shrink arbitrarily.
private val QUEUE_PANEL_MIN_WIDTH = 900.dp
private val SIDEBAR_COMPACT_MAX_WIDTH = 720.dp

/**
 * Top-level layout: sidebar + main content + optional queue panel on top, player bar pinned
 * to the bottom, with the update-check flow rendered as an overlay. Adapts to the window's
 * current size: the queue panel auto-hides and the sidebar collapses to an icon rail once
 * there isn't enough width to show them alongside real content.
 */
@Composable
fun AppShell() {
    val app = LocalApp.current
    var queueRequested by remember { mutableStateOf(true) }

    BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
        val compactSidebar = maxWidth < SIDEBAR_COMPACT_MAX_WIDTH
        val queueVisible = queueRequested && maxWidth >= QUEUE_PANEL_MIN_WIDTH

        Column(modifier = Modifier.fillMaxSize()) {
            Row(modifier = Modifier.weight(1f)) {
                Sidebar(compact = compactSidebar)
                Column(modifier = Modifier.weight(1f)) {
                    ConnectionBanner()
                    Box(modifier = Modifier.weight(1f)) {
                        when (val screen = app.navigation.collectAsState().value) {
                            Screen.Home -> HomeScreen()
                            Screen.Library -> LibraryScreen()
                            Screen.Albums -> AlbumsScreen()
                            is Screen.AlbumDetail -> AlbumDetailScreen(screen.albumTitle, screen.artist)
                            Screen.Playlists -> PlaylistsScreen()
                            is Screen.PlaylistDetail -> PlaylistDetailScreen(screen.playlistId)
                            Screen.Liked -> LikedScreen()
                            Screen.Catalog -> CatalogScreen()
                            Screen.Libraries -> LibrariesScreen()
                            is Screen.LibraryDetail -> LibraryDetailScreen(screen.libraryId)
                            Screen.Imports -> ImportsScreen()
                            Screen.Settings -> SettingsScreen()
                        }
                    }
                }
                AnimatedVisibility(visible = queueVisible) {
                    QueuePanel()
                }
            }
            PlayerBar(
                queueVisible = queueVisible,
                onToggleQueue = { queueRequested = !queueRequested },
            )
        }

        UpdateFlowHost()
    }
}
