package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.EmptyState
import pl.mekamb.music.desktop.ui.components.ScreenHeader
import pl.mekamb.music.desktop.ui.components.TrackRow

@Composable
fun LikedScreen() {
    val app = LocalApp.current
    val liked by app.likedTrackIds.collectAsState()
    val tracks by app.tracks.collectAsState()

    val likedTracks = remember(tracks, liked) { tracks.filter { it.id in liked } }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        ScreenHeader(title = "Liked tracks", subtitle = "${likedTracks.size} tracks")

        if (likedTracks.isEmpty()) {
            EmptyState("No liked tracks yet", "Tracks you like will show up here")
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                items(likedTracks) { track ->
                    TrackRow(
                        track = track,
                        contextTracks = likedTracks,
                        index = likedTracks.indexOf(track),
                    )
                }
            }
        }
    }
}
