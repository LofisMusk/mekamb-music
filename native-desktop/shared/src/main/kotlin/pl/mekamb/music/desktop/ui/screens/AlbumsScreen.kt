package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import pl.mekamb.music.desktop.api.Track
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.ArtworkImage
import pl.mekamb.music.desktop.ui.components.EmptyState
import pl.mekamb.music.desktop.ui.components.ScreenHeader
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.vm.Screen

private data class AlbumGroup(val title: String, val artist: String?, val tracks: List<Track>)

@Composable
fun AlbumsScreen() {
    val app = LocalApp.current
    val tracks by app.tracks.collectAsState()

    val albumGroups = remember(tracks) {
        tracks
            .groupBy { (it.album ?: "Unknown Album") + "|" + (it.artist ?: "") }
            .map { (_, groupTracks) ->
                val first = groupTracks.first()
                AlbumGroup(
                    title = first.album ?: "Unknown Album",
                    artist = first.artist,
                    tracks = groupTracks,
                )
            }
            .sortedBy { it.title }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        ScreenHeader(title = "Albums")

        if (albumGroups.isEmpty()) {
            EmptyState("No albums found")
        } else {
            LazyVerticalGrid(
                columns = GridCells.Adaptive(160.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                items(albumGroups) { group ->
                    AlbumCard(group = group, onClick = { app.navigate(Screen.AlbumDetail(group.title, group.artist)) })
                }
            }
        }
    }
}

@Composable
private fun AlbumCard(group: AlbumGroup, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = Color.Transparent,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            ArtworkImage(group.tracks.first().id, size = 140.dp)
            Text(
                group.title,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                group.artist ?: "Unknown Artist",
                style = MaterialTheme.typography.bodySmall,
                color = MekambColors.Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                "${group.tracks.size} tracks",
                style = MaterialTheme.typography.labelSmall,
                color = MekambColors.Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
