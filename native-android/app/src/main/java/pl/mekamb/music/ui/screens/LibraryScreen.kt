package pl.mekamb.music.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.AppUiState
import pl.mekamb.music.data.Album
import pl.mekamb.music.data.Playlist
import pl.mekamb.music.ui.components.ArtworkImage
import pl.mekamb.music.ui.components.FilterChipRow
import pl.mekamb.music.ui.components.ScreenTitle
import pl.mekamb.music.ui.theme.MekambColors

private val filters = listOf("All", "Playlists", "Albums", "Artists")

private sealed class LibraryItem {
    abstract val id: String
    abstract val name: String
    abstract val subtitle: String

    data class LikedSongs(val trackCount: Int) : LibraryItem() {
        override val id = "liked"
        override val name = "Liked Songs"
        override val subtitle = if (trackCount == 1) "Playlist · 1 song" else "Playlist · $trackCount songs"
    }
    data class PlaylistItem(val playlist: Playlist) : LibraryItem() {
        override val id = playlist.id
        override val name = playlist.name
        override val subtitle = "Playlist · ${playlist.trackCountText}"
    }
    data class AlbumItem(val album: Album) : LibraryItem() {
        override val id = album.id
        override val name = album.title
        override val subtitle = "Album · ${album.artist}"
    }
    data class ArtistItem(val artistName: String, val artworkTrackId: String?) : LibraryItem() {
        override val id = "artist:$artistName"
        override val name = artistName
        override val subtitle = "Artist"
    }
}

@Composable
fun LibraryScreen(
    uiState: AppUiState,
    endpoint: String,
    token: String,
    onOpenLiked: () -> Unit,
    onOpenAlbum: (String) -> Unit,
    onOpenArtist: (String) -> Unit,
) {
    var selectedFilter by remember { mutableStateOf("All") }

    val items = remember(uiState.tracks, uiState.albums, uiState.playlists, uiState.likedTrackIds, selectedFilter) {
        buildLibraryItems(uiState, selectedFilter)
    }

    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 18.dp),
        contentPadding = PaddingValues(top = 10.dp, bottom = 24.dp),
    ) {
        item { ScreenTitle("Your Library", Modifier.padding(bottom = 14.dp)) }
        item {
            FilterChipRow(filters, selectedFilter, onSelect = { selectedFilter = it }, modifier = Modifier.padding(bottom = 12.dp))
        }
        items(items, key = { it.id }) { entry ->
            fun onClick() {
                when (entry) {
                    is LibraryItem.LikedSongs -> onOpenLiked()
                    is LibraryItem.PlaylistItem -> Unit // no playlist-detail screen yet
                    is LibraryItem.AlbumItem -> onOpenAlbum(entry.album.id)
                    is LibraryItem.ArtistItem -> onOpenArtist(entry.artistName)
                }
            }
            LibraryRow(entry, endpoint, token, onClick = ::onClick)
        }
    }
}

@Composable
private fun LibraryRow(entry: LibraryItem, endpoint: String, token: String, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        when (entry) {
            is LibraryItem.LikedSongs -> Box(
                Modifier.size(50.dp).background(Brush.linearGradient(MekambColors.LikedHeroGradient), RoundedCornerShape(6.dp)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Filled.Favorite, contentDescription = null, tint = Color.White)
            }
            is LibraryItem.PlaylistItem -> ArtworkImage(entry.playlist.tracks.firstOrNull()?.id, endpoint, token, size = 50.dp, shape = RoundedCornerShape(6.dp), seed = entry.playlist.id)
            is LibraryItem.AlbumItem -> ArtworkImage(entry.album.tracks.firstOrNull()?.id, endpoint, token, size = 50.dp, shape = RoundedCornerShape(6.dp), seed = entry.album.id)
            is LibraryItem.ArtistItem -> ArtworkImage(entry.artworkTrackId, endpoint, token, size = 50.dp, shape = CircleShape, seed = entry.id)
        }
        Column(Modifier.weight(1f)) {
            Text(entry.name, color = MekambColors.TextPrimary, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(entry.subtitle, color = MekambColors.TextMuted, fontSize = 12.sp, modifier = Modifier.padding(top = 2.dp))
        }
        Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = Color(0xFF4A4F5A))
    }
}

private fun buildLibraryItems(uiState: AppUiState, filter: String): List<LibraryItem> {
    val result = mutableListOf<LibraryItem>()
    if (filter == "All" || filter == "Playlists") {
        result += LibraryItem.LikedSongs(uiState.likedTrackIds.size)
        result += uiState.playlists.map { LibraryItem.PlaylistItem(it) }
    }
    if (filter == "All" || filter == "Albums") {
        result += uiState.albums.map { LibraryItem.AlbumItem(it) }
    }
    if (filter == "Artists") {
        val byArtist = uiState.albums.groupBy { it.artist }
        result += byArtist.keys.sorted().map { name ->
            LibraryItem.ArtistItem(name, byArtist[name]?.firstOrNull()?.tracks?.firstOrNull()?.id)
        }
    }
    return result
}
