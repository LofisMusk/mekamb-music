package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.ArtworkImage
import pl.mekamb.music.desktop.ui.components.TrackRow
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.util.formatDuration
import pl.mekamb.music.desktop.vm.Screen

@Composable
fun AlbumDetailScreen(albumTitle: String, artist: String?) {
    val app = LocalApp.current
    val tracks by app.tracks.collectAsState()

    val albumTracks = remember(tracks, albumTitle, artist) {
        tracks
            .filter { (it.album ?: "Unknown Album") == albumTitle && it.artist == artist }
            .sortedBy { it.title }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        IconButton(onClick = { app.navigate(Screen.Albums) }) {
            Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
        }

        Row(
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            ArtworkImage(albumTracks.firstOrNull()?.id, size = 200.dp)
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(albumTitle, style = MaterialTheme.typography.headlineMedium)
                Text(
                    artist ?: "Unknown Artist",
                    style = MaterialTheme.typography.titleMedium,
                    color = MekambColors.Muted,
                )
                Text(
                    "${albumTracks.size} tracks · ${formatDuration(albumTracks.sumOf { it.durationSeconds ?: 0.0 })}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MekambColors.Muted,
                )
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(onClick = { app.player.playTracks(albumTracks) }) {
                Icon(Icons.Filled.PlayArrow, contentDescription = null)
                Text(" Play")
            }
            OutlinedButton(onClick = { app.downloads.downloadTracks(albumTracks) }) {
                Icon(Icons.Filled.Download, contentDescription = null)
                Text(" Download all")
            }
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            items(albumTracks) { track ->
                TrackRow(
                    track = track,
                    contextTracks = albumTracks,
                    index = albumTracks.indexOf(track),
                    showArt = false,
                )
            }
        }
    }
}
