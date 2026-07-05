package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.api.PlaylistDetail
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.EmptyState
import pl.mekamb.music.desktop.ui.components.LoadingState
import pl.mekamb.music.desktop.ui.components.TrackRow
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.vm.Screen

@Composable
fun PlaylistDetailScreen(playlistId: String) {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()

    var detail by remember(playlistId) { mutableStateOf<PlaylistDetail?>(null) }

    suspend fun reload() {
        detail = runCatching { app.api.getPlaylist(playlistId) }.getOrNull()
    }

    LaunchedEffect(playlistId) { reload() }

    val current = detail
    if (current == null) {
        LoadingState()
        return
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        IconButton(onClick = { app.navigate(Screen.Playlists) }) {
            Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
        }

        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(current.name, style = MaterialTheme.typography.headlineMedium)
            Text(
                "${current.tracks.size} tracks",
                style = MaterialTheme.typography.bodyMedium,
                color = MekambColors.Muted,
            )
        }

        Button(onClick = { app.player.playTracks(current.tracks.map { it.track }) }) {
            Icon(Icons.Filled.PlayArrow, contentDescription = null)
            Text(" Play")
        }

        if (current.tracks.isEmpty()) {
            EmptyState("This playlist is empty")
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                itemsIndexed(current.tracks, key = { _, item -> item.track.id }) { i, item ->
                    TrackRow(
                        track = item.track,
                        contextTracks = current.tracks.map { it.track },
                        index = i,
                        trailing = {
                            Row {
                                IconButton(
                                    onClick = {
                                        val ids = current.tracks.map { it.track.id }.toMutableList()
                                        val tmp = ids[i]
                                        ids[i] = ids[i - 1]
                                        ids[i - 1] = tmp
                                        scope.launch {
                                            runCatching { app.api.reorderPlaylist(playlistId, ids) }
                                            reload()
                                        }
                                    },
                                    enabled = i > 0,
                                ) {
                                    Icon(Icons.Filled.KeyboardArrowUp, contentDescription = "Move up")
                                }
                                IconButton(
                                    onClick = {
                                        val ids = current.tracks.map { it.track.id }.toMutableList()
                                        val tmp = ids[i]
                                        ids[i] = ids[i + 1]
                                        ids[i + 1] = tmp
                                        scope.launch {
                                            runCatching { app.api.reorderPlaylist(playlistId, ids) }
                                            reload()
                                        }
                                    },
                                    enabled = i < current.tracks.lastIndex,
                                ) {
                                    Icon(Icons.Filled.KeyboardArrowDown, contentDescription = "Move down")
                                }
                                IconButton(
                                    onClick = {
                                        scope.launch {
                                            runCatching {
                                                app.api.removeTrackFromPlaylist(playlistId, item.track.id)
                                            }
                                            reload()
                                        }
                                    },
                                ) {
                                    Icon(Icons.Filled.Close, contentDescription = "Remove")
                                }
                            }
                        },
                    )
                }
            }
        }
    }
}
