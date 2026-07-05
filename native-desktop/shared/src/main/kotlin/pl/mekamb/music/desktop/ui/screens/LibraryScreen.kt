package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import pl.mekamb.music.desktop.api.Track
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.EmptyState
import pl.mekamb.music.desktop.ui.components.LoadingState
import pl.mekamb.music.desktop.ui.components.ScreenHeader
import pl.mekamb.music.desktop.ui.components.SearchField
import pl.mekamb.music.desktop.ui.components.TrackRow

private enum class LibrarySort { RECENTLY_ADDED, TITLE, ARTIST }

@Composable
fun LibraryScreen() {
    val app = LocalApp.current
    val tracks by app.tracks.collectAsState()
    val libraryLoading by app.libraryLoading.collectAsState()

    var query by remember { mutableStateOf("") }
    var debouncedQuery by remember { mutableStateOf("") }
    var sort by remember { mutableStateOf(LibrarySort.RECENTLY_ADDED) }

    LaunchedEffect(query) {
        delay(350)
        debouncedQuery = query
    }

    val filteredSorted = remember(tracks, debouncedQuery, sort) {
        val filtered = if (debouncedQuery.isBlank()) {
            tracks
        } else {
            tracks.filter {
                it.title.contains(debouncedQuery, ignoreCase = true) ||
                    (it.artist?.contains(debouncedQuery, ignoreCase = true) ?: false) ||
                    (it.album?.contains(debouncedQuery, ignoreCase = true) ?: false)
            }
        }
        when (sort) {
            LibrarySort.RECENTLY_ADDED -> filtered.sortedByDescending { it.createdAt ?: "" }
            LibrarySort.TITLE -> filtered.sortedBy { it.title }
            LibrarySort.ARTIST -> filtered.sortedBy { it.artist ?: "" }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        ScreenHeader(title = "Library", subtitle = "${tracks.size} tracks")

        SearchField(
            value = query,
            onValueChange = { query = it },
            placeholder = "Search by title, artist or album",
            modifier = Modifier.fillMaxWidth(),
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = sort == LibrarySort.RECENTLY_ADDED,
                onClick = { sort = LibrarySort.RECENTLY_ADDED },
                label = { androidx.compose.material3.Text("Recently added") },
            )
            FilterChip(
                selected = sort == LibrarySort.TITLE,
                onClick = { sort = LibrarySort.TITLE },
                label = { androidx.compose.material3.Text("Title") },
            )
            FilterChip(
                selected = sort == LibrarySort.ARTIST,
                onClick = { sort = LibrarySort.ARTIST },
                label = { androidx.compose.material3.Text("Artist") },
            )
        }

        when {
            libraryLoading && tracks.isEmpty() -> LoadingState()
            filteredSorted.isEmpty() -> EmptyState("No tracks found")
            else -> LazyColumn(
                verticalArrangement = Arrangement.spacedBy(4.dp),
                contentPadding = PaddingValues(vertical = 8.dp),
            ) {
                items(filteredSorted) { track ->
                    TrackRow(
                        track = track,
                        contextTracks = filteredSorted,
                        index = filteredSorted.indexOf(track),
                    )
                }
            }
        }
    }
}
