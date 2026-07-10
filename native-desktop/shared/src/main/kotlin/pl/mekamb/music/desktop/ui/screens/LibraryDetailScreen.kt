package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.api.LibraryDetail
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.EmptyState
import pl.mekamb.music.desktop.ui.components.LoadingState
import pl.mekamb.music.desktop.ui.components.TrackRow
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.vm.Screen

@Composable
fun LibraryDetailScreen(libraryId: String) {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()

    var detail by remember(libraryId) { mutableStateOf<LibraryDetail?>(null) }

    suspend fun reload() {
        detail = runCatching { app.api.getLibrary(libraryId) }.getOrNull()
    }

    LaunchedEffect(libraryId) { reload() }

    val current = detail
    if (current == null) {
        LoadingState()
        return
    }

    val tracks = current.tracks.sortedBy { it.position }.map { it.track }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        IconButton(onClick = { app.navigate(Screen.Libraries) }) {
            Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
        }

        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(current.name, style = MaterialTheme.typography.headlineMedium)
            Text("${tracks.size} tracks", style = MaterialTheme.typography.bodyMedium, color = MekambColors.Muted)
        }

        Button(onClick = { app.player.playTracks(tracks) }) {
            Icon(Icons.Filled.PlayArrow, contentDescription = null)
            Text(" Play")
        }

        if (tracks.isEmpty()) {
            EmptyState("This library is empty", "Add tracks from the shared catalog using the track menu.")
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                itemsIndexed(tracks, key = { _, track -> track.id }) { i, track ->
                    TrackRow(
                        track = track,
                        contextTracks = tracks,
                        index = i,
                        trailing = {
                            IconButton(onClick = {
                                scope.launch {
                                    runCatching { app.api.removeTrackFromLibrary(libraryId, track.id) }
                                    reload()
                                    app.loadLibraries()
                                }
                            }) {
                                Icon(Icons.Filled.Close, contentDescription = "Remove")
                            }
                        },
                    )
                }
            }
        }
    }
}
