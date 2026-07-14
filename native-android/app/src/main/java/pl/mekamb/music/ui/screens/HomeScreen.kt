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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.AppUiState
import pl.mekamb.music.data.Album
import pl.mekamb.music.data.DailyMix
import pl.mekamb.music.data.Playlist
import pl.mekamb.music.ui.components.ArtworkImage
import pl.mekamb.music.ui.components.GradientTile
import pl.mekamb.music.ui.components.MixBadge
import pl.mekamb.music.ui.theme.MekambColors
import java.util.Calendar

@Composable
fun HomeScreen(
    uiState: AppUiState,
    endpoint: String,
    token: String,
    onOpenImports: () -> Unit,
    onOpenAvatar: () -> Unit,
    onOpenSearch: () -> Unit,
    onOpenLiked: () -> Unit,
    onOpenAlbum: (String) -> Unit,
    onOpenMix: (String) -> Unit,
) {
    val greeting = remember { greetingForHour() }
    val recentAlbums = remember(uiState.albums) { recentlyAddedAlbums(uiState.albums) }
    val pins = remember(uiState.albums, uiState.playlists) {
        homePins(uiState.albums, uiState.playlists, onOpenLiked = onOpenLiked, onOpenAlbum = onOpenAlbum)
    }

    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 18.dp),
        verticalArrangement = Arrangement.spacedBy(22.dp),
        contentPadding = PaddingValues(top = 10.dp, bottom = 24.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(greeting, color = MekambColors.TextPrimary, fontSize = 23.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.weight(1f))
                Box(
                    Modifier
                        .size(34.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(MekambColors.SurfaceAlt)
                        .clickable { onOpenImports() },
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Filled.Download, contentDescription = "Imports", tint = MekambColors.TextMuted, modifier = Modifier.size(17.dp))
                    if (uiState.activeImportCount > 0) {
                        Box(
                            Modifier.align(Alignment.TopEnd).size(15.dp).clip(CircleShape).background(MekambColors.Accent),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(if (uiState.activeImportCount > 9) "9+" else "${uiState.activeImportCount}", color = MekambColors.BackgroundAlt, fontSize = 9.sp, fontWeight = FontWeight.ExtraBold)
                        }
                    }
                }
                Spacer(Modifier.width(10.dp))
                Box(
                    Modifier
                        .size(34.dp)
                        .clip(CircleShape)
                        .background(Brush.linearGradient(MekambColors.AvatarGradient))
                        .clickable { onOpenAvatar() },
                    contentAlignment = Alignment.Center,
                ) {
                    Text(initialsFor(uiState.accountUsername), color = MekambColors.BackgroundAlt, fontSize = 12.sp, fontWeight = FontWeight.ExtraBold)
                }
            }
        }
        item {
            Row(
                Modifier
                    .fillMaxWidth()
                    .height(40.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(MekambColors.SurfaceAlt)
                    .clickable { onOpenSearch() }
                    .padding(horizontal = 13.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Filled.Search, contentDescription = null, tint = MekambColors.TextMuted, modifier = Modifier.size(15.dp))
                Spacer(Modifier.width(10.dp))
                Text("Search tracks, albums, artists", color = MekambColors.TextMuted, fontSize = 13.5.sp)
            }
        }
        items(pins.chunked(2)) { rowPins ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                rowPins.forEach { pin -> PinTile(pin, endpoint, token, Modifier.weight(1f)) }
                if (rowPins.size == 1) Spacer(Modifier.weight(1f))
            }
        }
        if (uiState.dailyMixes.isNotEmpty()) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Made for you", color = MekambColors.TextPrimary, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        items(uiState.dailyMixes) { mix -> MixCard(mix, onClick = { onOpenMix(mix.id) }) }
                    }
                }
            }
        }
        if (recentAlbums.isNotEmpty()) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Recently added", color = MekambColors.TextPrimary, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        items(recentAlbums) { album ->
                            Column(
                                Modifier.width(132.dp).clickable { onOpenAlbum(album.id) },
                                verticalArrangement = Arrangement.spacedBy(7.dp),
                            ) {
                                ArtworkImage(album.tracks.firstOrNull()?.id, endpoint, token, size = 132.dp, seed = album.id)
                                Text(album.title, color = MekambColors.TextPrimary, fontSize = 12.5.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(album.artist, color = MekambColors.TextMuted, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PinTile(pin: HomePin, endpoint: String, token: String, modifier: Modifier = Modifier) {
    Row(
        modifier
            .height(48.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(MekambColors.SurfaceElevated)
            .clickable { pin.onClick() },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (pin.isLiked) {
            Box(Modifier.size(48.dp).background(Brush.linearGradient(MekambColors.LikedHeroGradient)), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Favorite, contentDescription = null, tint = Color.White, modifier = Modifier.size(17.dp))
            }
        } else if (pin.trackIdForArt != null) {
            ArtworkImage(pin.trackIdForArt, endpoint, token, size = 48.dp, shape = RoundedCornerShape(0.dp), seed = pin.seed)
        } else {
            GradientTile(pin.seed, size = 48.dp, shape = RoundedCornerShape(0.dp))
        }
        Text(
            pin.name,
            color = MekambColors.TextPrimary,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(horizontal = 9.dp),
        )
    }
}

@Composable
private fun MixCard(mix: DailyMix, onClick: () -> Unit) {
    Column(Modifier.width(132.dp).clickable(onClick = onClick), verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Box(
            Modifier
                .size(132.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(Brush.linearGradient(listOf(MekambColors.AccentDeep, MekambColors.Accent))),
        ) {
            MixBadge(Modifier.padding(7.dp))
        }
        Text(mix.title, color = MekambColors.TextPrimary, fontSize = 12.5.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(mix.description, color = MekambColors.TextMuted, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

private fun greetingForHour(): String {
    val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
    return when {
        hour < 12 -> "Good morning"
        hour < 18 -> "Good afternoon"
        else -> "Good evening"
    }
}

private fun initialsFor(name: String): String {
    val parts = name.trim().split(Regex("\\s+")).filter { it.isNotBlank() }
    if (parts.isEmpty()) return "?"
    return if (parts.size == 1) parts[0].take(2).uppercase() else (parts[0].take(1) + parts[1].take(1)).uppercase()
}

private data class HomePin(val name: String, val isLiked: Boolean, val trackIdForArt: String?, val seed: String, val onClick: () -> Unit)

private fun homePins(
    albums: List<Album>,
    playlists: List<Playlist>,
    onOpenLiked: () -> Unit,
    onOpenAlbum: (String) -> Unit,
): List<HomePin> {
    val pins = mutableListOf<HomePin>()
    pins += HomePin("Liked Songs", isLiked = true, trackIdForArt = null, seed = "liked", onClick = onOpenLiked)
    playlists.take(3).forEach { playlist ->
        pins += HomePin(playlist.name, isLiked = false, trackIdForArt = playlist.tracks.firstOrNull()?.id, seed = playlist.id, onClick = {})
    }
    recentlyAddedAlbums(albums).take(4).forEach { album ->
        pins += HomePin(album.title, isLiked = false, trackIdForArt = album.tracks.firstOrNull()?.id, seed = album.id, onClick = { onOpenAlbum(album.id) })
    }
    return pins
}

private fun recentlyAddedAlbums(albums: List<Album>): List<Album> =
    albums.sortedByDescending { album -> album.tracks.maxOfOrNull { it.createdAt ?: "" } ?: "" }
