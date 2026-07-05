package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import java.time.LocalTime
import pl.mekamb.music.desktop.api.DailyMix
import pl.mekamb.music.desktop.api.PersonalizedHomeResponse
import pl.mekamb.music.desktop.api.RecommendationTrackItem
import pl.mekamb.music.desktop.api.Track
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.ArtworkImage
import pl.mekamb.music.desktop.ui.theme.MekambColors

@Composable
fun HomeScreen() {
    val app = LocalApp.current
    val tracks by app.tracks.collectAsState()
    val offlineIds by app.downloads.offlineTrackIds.collectAsState()

    var personalized by remember { mutableStateOf<PersonalizedHomeResponse?>(null) }

    LaunchedEffect(Unit) {
        personalized = runCatching { app.api.personalizedHome(localLimit = 24, mixCount = 4, mixSize = 12) }
            .getOrNull()
    }

    val hour = remember { LocalTime.now().hour }
    val greeting = when {
        hour < 12 -> "Good morning"
        hour < 18 -> "Good afternoon"
        else -> "Good evening"
    }

    val recommendedTracks = personalized?.recommendedTracks.orEmpty()
    val dailyMixes = personalized?.dailyMixes.orEmpty()
    val recentlyAdded = remember(tracks) { tracks.sortedByDescending { it.createdAt ?: "" }.take(20) }
    val offlineTracks = remember(tracks, offlineIds) { tracks.filter { it.id in offlineIds } }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Column {
            Text(greeting, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(
                "Welcome back to Mekamb Music",
                style = MaterialTheme.typography.bodyMedium,
                color = MekambColors.Muted,
            )
        }

        if (recommendedTracks.isNotEmpty()) {
            HomeSection(title = "Made for you") {
                items(recommendedTracks) { item ->
                    RecommendationCard(
                        item = item,
                        onClick = {
                            app.player.playTracks(
                                recommendedTracks.map { it.track },
                                recommendedTracks.indexOf(item),
                            )
                        },
                    )
                }
            }
        }

        if (dailyMixes.isNotEmpty()) {
            HomeSection(title = "Daily Mixes") {
                items(dailyMixes) { mix ->
                    DailyMixCard(
                        mix = mix,
                        onClick = { app.player.playTracks(mix.tracks.map { it.track }) },
                    )
                }
            }
        }

        if (recentlyAdded.isNotEmpty()) {
            HomeSection(title = "Recently added") {
                items(recentlyAdded) { track ->
                    TrackCard(
                        track = track,
                        subtitle = track.artist ?: "Unknown artist",
                        onClick = { app.player.playTracks(recentlyAdded, recentlyAdded.indexOf(track)) },
                    )
                }
            }
        }

        if (offlineTracks.isNotEmpty()) {
            HomeSection(title = "Available offline") {
                items(offlineTracks) { track ->
                    TrackCard(
                        track = track,
                        subtitle = track.artist ?: "Unknown artist",
                        onClick = { app.player.playTracks(offlineTracks, offlineTracks.indexOf(track)) },
                    )
                }
            }
        }
    }
}

@Composable
private fun HomeSection(
    title: String,
    content: androidx.compose.foundation.lazy.LazyListScope.() -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        LazyRow(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(vertical = 4.dp),
            content = content,
        )
    }
}

@Composable
private fun RecommendationCard(item: RecommendationTrackItem, onClick: () -> Unit) {
    TrackCard(
        track = item.track,
        subtitle = item.reasons.firstOrNull() ?: "Recommended",
        onClick = onClick,
    )
}

@Composable
private fun DailyMixCard(mix: DailyMix, onClick: () -> Unit) {
    androidx.compose.material3.Surface(
        onClick = onClick,
        color = Color.Transparent,
        modifier = Modifier.width(150.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            ArtworkImage(mix.tracks.firstOrNull()?.track?.id, size = 150.dp)
            Text(
                mix.title,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                mix.description ?: mix.seedLabel ?: "",
                style = MaterialTheme.typography.bodySmall,
                color = MekambColors.Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun TrackCard(track: Track, subtitle: String, onClick: () -> Unit) {
    androidx.compose.material3.Surface(
        onClick = onClick,
        color = Color.Transparent,
        modifier = Modifier.width(150.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            ArtworkImage(track.id, size = 150.dp)
            Text(
                track.title,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = MekambColors.Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
