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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Shuffle
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.AppUiState
import pl.mekamb.music.data.ApiTrack
import pl.mekamb.music.data.PlaybackSnapshot
import pl.mekamb.music.ui.components.ArtworkImage
import pl.mekamb.music.ui.components.BackIconButton
import pl.mekamb.music.ui.components.BigPlayButton
import pl.mekamb.music.ui.components.CircleIconButton
import pl.mekamb.music.ui.components.LikeButton
import pl.mekamb.music.ui.components.TrackIndexOrEqualizer
import pl.mekamb.music.ui.components.TrackRow
import pl.mekamb.music.ui.components.formatDuration
import pl.mekamb.music.ui.components.heroBrushForSeed
import pl.mekamb.music.ui.theme.MekambColors
import kotlin.math.roundToInt

@Composable
fun AlbumScreen(
    albumId: String,
    uiState: AppUiState,
    playback: PlaybackSnapshot,
    endpoint: String,
    token: String,
    onBack: () -> Unit,
    onOpenArtist: (String) -> Unit,
    onPlay: (ApiTrack, List<ApiTrack>) -> Unit,
    onToggleLike: (ApiTrack) -> Unit,
) {
    val album = uiState.albums.firstOrNull { it.id == albumId } ?: run {
        Column(Modifier.fillMaxSize().padding(18.dp)) {
            BackIconButton(onBack)
            Spacer(Modifier.height(24.dp))
            Text("Album not found.", color = MekambColors.TextMuted)
        }
        return
    }
    val totalMinutes = remember(album) { (album.tracks.sumOf { it.durationSeconds ?: 0.0 } / 60.0).roundToInt() }
    val year = remember(album) { album.tracks.firstOrNull()?.createdAt?.take(4) }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
        item {
            Column(
                Modifier
                    .fillMaxWidth()
                    .background(heroBrushForSeed(album.id, MekambColors.Background))
                    .padding(top = 8.dp, bottom = 20.dp, start = 18.dp, end = 18.dp),
            ) {
                BackIconButton(onBack)
                Spacer(Modifier.height(14.dp))
                Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                    ArtworkImage(album.tracks.firstOrNull()?.id, endpoint, token, size = 208.dp, shape = RoundedCornerShape(10.dp), seed = album.id)
                    Spacer(Modifier.height(14.dp))
                    Text(album.title, color = MekambColors.TextPrimary, fontSize = 21.sp, fontWeight = FontWeight.ExtraBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(
                        album.artist,
                        color = MekambColors.Link,
                        fontSize = 13.5.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(top = 5.dp).clickable { onOpenArtist(album.artist) },
                    )
                    val metaLine = listOfNotNull(year, "${album.tracks.size} tracks", "$totalMinutes min").joinToString(" · ")
                    Text(metaLine, color = MekambColors.TextMuted, fontSize = 11.5.sp, modifier = Modifier.padding(top = 5.dp))
                }
            }
        }
        item {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.Center,
            ) {
                CircleIconButton(Icons.Filled.Shuffle, onClick = {
                    val shuffled = album.tracks.shuffled()
                    shuffled.firstOrNull()?.let { onPlay(it, shuffled) }
                })
                Spacer(Modifier.size(16.dp))
                BigPlayButton(isPlaying = playback.isPlaying && playback.currentTrack?.let { cur -> album.tracks.any { it.id == cur.id } } == true, onClick = {
                    album.tracks.firstOrNull()?.let { onPlay(it, album.tracks) }
                })
                Spacer(Modifier.size(16.dp))
                CircleIconButton(Icons.Filled.MoreVert, onClick = {})
            }
        }
        items(album.tracks, key = { it.id }) { track ->
            val index = album.tracks.indexOf(track) + 1
            val isCurrent = playback.currentTrack?.id == track.id
            Box(Modifier.padding(horizontal = 18.dp)) {
                TrackRow(
                    title = track.title,
                    subtitle = formatDuration(track.durationSeconds),
                    isCurrent = isCurrent,
                    onClick = { onPlay(track, album.tracks) },
                    leading = { TrackIndexOrEqualizer(index, isCurrent) },
                    trailing = { LikeButton(uiState.likedTrackIds.contains(track.id), onToggle = { onToggleLike(track) }) },
                )
            }
        }
    }
}
