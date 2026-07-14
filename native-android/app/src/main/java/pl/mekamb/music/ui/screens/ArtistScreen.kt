package pl.mekamb.music.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Shuffle
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.AppUiState
import pl.mekamb.music.AppViewModel
import pl.mekamb.music.data.Artist
import pl.mekamb.music.data.ApiTrack
import pl.mekamb.music.data.PlaybackSnapshot
import pl.mekamb.music.ui.components.ArtworkImage
import pl.mekamb.music.ui.components.BackIconButton
import pl.mekamb.music.ui.components.BigPlayButton
import pl.mekamb.music.ui.components.TrackRow
import pl.mekamb.music.ui.components.formatDuration
import pl.mekamb.music.ui.components.heroBrushForSeed
import pl.mekamb.music.ui.theme.MekambColors

@Composable
fun ArtistScreen(
    artistName: String,
    uiState: AppUiState,
    playback: PlaybackSnapshot,
    endpoint: String,
    token: String,
    viewModel: AppViewModel,
    onBack: () -> Unit,
    onOpenAlbum: (String) -> Unit,
    onPlay: (ApiTrack, List<ApiTrack>) -> Unit,
) {
    var artist by remember(artistName) { mutableStateOf<Artist?>(null) }

    LaunchedEffect(artistName) {
        viewModel.loadArtist(artistName) { artist = it }
    }

    val resolved = artist ?: Artist(artistName, uiState.albums.filter { it.artist == artistName }, emptyList())
    val heroTrackId = resolved.albums.firstOrNull()?.tracks?.firstOrNull()?.id

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
        item {
            Column(
                Modifier
                    .fillMaxWidth()
                    .height(200.dp)
                    .background(heroBrushForSeed(heroTrackId ?: artistName, MekambColors.Background))
                    .padding(horizontal = 18.dp, vertical = 8.dp),
            ) {
                BackIconButton(onBack)
                Spacer(Modifier.weight(1f))
                Text("ARTIST", color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.72f), fontSize = 10.5.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 1.3.sp)
                Text(resolved.name, color = MekambColors.TextPrimary, fontSize = 32.sp, fontWeight = FontWeight.ExtraBold, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 4.dp))
                val albumWord = if (resolved.albums.size == 1) "album" else "albums"
                Text("${resolved.albums.size} $albumWord in your library", color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.72f), fontSize = 12.sp, modifier = Modifier.padding(top = 5.dp, bottom = 14.dp))
            }
        }
        item {
            Row(Modifier.padding(horizontal = 18.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                BigPlayButton(isPlaying = false, size = 48.dp, onClick = {
                    val first = resolved.topTracks.firstOrNull() ?: resolved.albums.firstOrNull()?.tracks?.firstOrNull()
                    first?.let { onPlay(it, resolved.topTracks.ifEmpty { resolved.albums.flatMap { a -> a.tracks } }) }
                })
                Spacer(Modifier.width(12.dp))
                Row(
                    Modifier
                        .height(36.dp)
                        .background(androidx.compose.ui.graphics.Color.Transparent, RoundedCornerShape(18.dp))
                        .padding(horizontal = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Filled.Shuffle, contentDescription = null, tint = MekambColors.TextMuted, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(7.dp))
                    Text("Shuffle", color = MekambColors.TextMuted, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
        if (resolved.topTracks.isNotEmpty()) {
            item {
                Text("Popular", color = MekambColors.TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(horizontal = 18.dp, top = 8.dp, bottom = 8.dp))
            }
            items(resolved.topTracks, key = { it.id }) { track ->
                val isCurrent = playback.currentTrack?.id == track.id
                Box(Modifier.padding(horizontal = 18.dp)) {
                    TrackRow(
                        title = track.title,
                        subtitle = track.displayAlbum,
                        isCurrent = isCurrent,
                        onClick = { onPlay(track, resolved.topTracks) },
                        leading = { ArtworkImage(track.id, endpoint, token, size = 44.dp, shape = RoundedCornerShape(6.dp)) },
                        trailing = { Text(formatDuration(track.durationSeconds), color = MekambColors.TextMuted, fontSize = 12.sp) },
                    )
                }
            }
        }
        if (resolved.albums.isNotEmpty()) {
            item {
                Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("In your library", color = MekambColors.TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(horizontal = 18.dp))
                    LazyRow(
                        contentPadding = PaddingValues(horizontal = 18.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        items(resolved.albums, key = { it.id }) { album ->
                            Column(
                                Modifier.width(124.dp).clickable { onOpenAlbum(album.id) },
                                verticalArrangement = Arrangement.spacedBy(7.dp),
                            ) {
                                ArtworkImage(album.tracks.firstOrNull()?.id, endpoint, token, size = 124.dp, seed = album.id)
                                Text(album.title, color = MekambColors.TextPrimary, fontSize = 12.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(album.tracks.firstOrNull()?.createdAt?.take(4) ?: "", color = MekambColors.TextMuted, fontSize = 11.sp)
                            }
                        }
                    }
                }
            }
        }
    }
}
