package pl.mekamb.music.ui.nav

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.LibraryMusic
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import pl.mekamb.music.AppViewModel
import pl.mekamb.music.data.PlaybackSnapshot
import pl.mekamb.music.ui.components.ArtworkImage
import pl.mekamb.music.ui.screens.AddMusicScreen
import pl.mekamb.music.ui.screens.AlbumScreen
import pl.mekamb.music.ui.screens.ArtistScreen
import pl.mekamb.music.ui.screens.HomeScreen
import pl.mekamb.music.ui.screens.ImportsScreen
import pl.mekamb.music.ui.screens.LibraryScreen
import pl.mekamb.music.ui.screens.LikedScreen
import pl.mekamb.music.ui.screens.MixScreen
import pl.mekamb.music.ui.screens.NowPlayingScreen
import pl.mekamb.music.ui.screens.ProfileMenuOverlay
import pl.mekamb.music.ui.screens.SettingsScreen
import pl.mekamb.music.ui.theme.MekambColors

private object Routes {
    const val Home = "home"
    const val Library = "library"
    const val AddMusic = "addMusic"
    const val Imports = "imports"
    const val Liked = "liked"
    const val Settings = "settings"
    const val Album = "album/{albumId}"
    const val Artist = "artist/{artistName}"
    const val Mix = "mix/{mixId}"

    /** "Pushed" screens get no persistent bottom-tab highlight, matching the design (`!s.view`). */
    val pushed = setOf(Liked, Settings, Album, Artist, Mix)
}

private data class TabSpec(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    TabSpec(Routes.Home, "Home", Icons.Filled.Home),
    TabSpec(Routes.Library, "Library", Icons.Filled.LibraryMusic),
    TabSpec(Routes.AddMusic, "Add Music", Icons.Filled.Add),
    TabSpec(Routes.Imports, "Imports", Icons.Filled.Download),
)

@Composable
fun MekambApp(viewModel: AppViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val playback by viewModel.playbackState.collectAsStateWithLifecycle()
    val navController = rememberNavController()
    var showProfileMenu by remember { mutableStateOf(false) }
    var showNowPlaying by remember { mutableStateOf(false) }

    BackHandler(enabled = showNowPlaying) { showNowPlaying = false }
    // Guards against an empty overlay if playback stops (queue end, error) while the sheet is open.
    androidx.compose.runtime.LaunchedEffect(playback.currentTrack) {
        if (playback.currentTrack == null) showNowPlaying = false
    }

    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route ?: Routes.Home
    val activeTabRoute = if (currentRoute in Routes.pushed) null else currentRoute
    val endpoint = remember(uiState.apiEndpoint) { normalizedEndpointFor(uiState.apiEndpoint) }
    val token = uiState.apiToken
    val isCurrentLiked = playback.currentTrack?.id?.let { uiState.likedTrackIds.contains(it) } ?: false

    Box(Modifier.fillMaxSize().background(MekambColors.Background)) {
        Column(
            Modifier
                .fillMaxSize()
                .statusBarsPadding()
        ) {
            Box(Modifier.weight(1f)) {
                NavHost(navController = navController, startDestination = Routes.Home) {
                    composable(Routes.Home) {
                        HomeScreen(
                            uiState = uiState,
                            endpoint = endpoint,
                            token = token,
                            onOpenImports = { navigateTab(navController, Routes.Imports) },
                            onOpenAvatar = { showProfileMenu = true },
                            onOpenSearch = { navigateTab(navController, Routes.Library) },
                            onOpenLiked = { navController.navigate(Routes.Liked) },
                            onOpenAlbum = { id -> navController.navigate("album/$id") },
                            onOpenMix = { id -> navController.navigate("mix/$id") },
                        )
                    }
                    composable(Routes.Library) {
                        LibraryScreen(
                            uiState = uiState,
                            endpoint = endpoint,
                            token = token,
                            onOpenLiked = { navController.navigate(Routes.Liked) },
                            onOpenAlbum = { id -> navController.navigate("album/$id") },
                            onOpenArtist = { name -> navController.navigate("artist/${android.net.Uri.encode(name)}") },
                        )
                    }
                    composable(Routes.AddMusic) {
                        AddMusicScreen(uiState = uiState, viewModel = viewModel)
                    }
                    composable(Routes.Imports) {
                        ImportsScreen(uiState = uiState, viewModel = viewModel)
                    }
                    composable(Routes.Liked) {
                        LikedScreen(
                            uiState = uiState,
                            playback = playback,
                            endpoint = endpoint,
                            token = token,
                            onBack = { navController.popBackStack() },
                            onPlay = { track, queue -> viewModel.playTrack(track, queue) },
                            onToggleLike = { viewModel.toggleLike(it) },
                        )
                    }
                    composable(Routes.Settings) {
                        SettingsScreen(uiState = uiState, viewModel = viewModel, onBack = { navController.popBackStack() })
                    }
                    composable(Routes.Album) { entry ->
                        val albumId = entry.arguments?.getString("albumId").orEmpty()
                        AlbumScreen(
                            albumId = albumId,
                            uiState = uiState,
                            playback = playback,
                            endpoint = endpoint,
                            token = token,
                            onBack = { navController.popBackStack() },
                            onOpenArtist = { name -> navController.navigate("artist/${android.net.Uri.encode(name)}") },
                            onPlay = { track, queue -> viewModel.playTrack(track, queue) },
                            onToggleLike = { viewModel.toggleLike(it) },
                        )
                    }
                    composable(Routes.Artist) { entry ->
                        val artistName = android.net.Uri.decode(entry.arguments?.getString("artistName").orEmpty())
                        ArtistScreen(
                            artistName = artistName,
                            uiState = uiState,
                            playback = playback,
                            endpoint = endpoint,
                            token = token,
                            viewModel = viewModel,
                            onBack = { navController.popBackStack() },
                            onOpenAlbum = { id -> navController.navigate("album/$id") },
                            onPlay = { track, queue -> viewModel.playTrack(track, queue) },
                        )
                    }
                    composable(Routes.Mix) { entry ->
                        val mixId = entry.arguments?.getString("mixId").orEmpty()
                        MixScreen(
                            mixId = mixId,
                            uiState = uiState,
                            playback = playback,
                            endpoint = endpoint,
                            token = token,
                            onBack = { navController.popBackStack() },
                            onPlay = { track, queue -> viewModel.playTrack(track, queue) },
                            onToggleLike = { viewModel.toggleLike(it) },
                        )
                    }
                }
            }
            BottomBarWithMiniPlayer(
                activeRoute = activeTabRoute,
                playback = playback,
                endpoint = endpoint,
                token = token,
                isLiked = isCurrentLiked,
                activeImportCount = uiState.activeImportCount,
                onTabSelected = { route -> navigateTab(navController, route) },
                onTogglePlay = { viewModel.togglePlayback() },
                onToggleLike = { viewModel.currentApiTrack()?.let { viewModel.toggleLike(it) } },
                onExpand = { showNowPlaying = true },
            )
        }

        if (showProfileMenu) {
            ProfileMenuOverlay(
                username = uiState.accountUsername,
                email = uiState.accountEmail,
                onDismiss = { showProfileMenu = false },
                onOpenSettings = {
                    showProfileMenu = false
                    navController.navigate(Routes.Settings)
                },
                onLogout = {
                    showProfileMenu = false
                    viewModel.logout()
                },
            )
        }

        if (showNowPlaying) {
            NowPlayingScreen(
                uiState = uiState,
                playback = playback,
                endpoint = endpoint,
                token = token,
                onClose = { showNowPlaying = false },
                onTogglePlay = { viewModel.togglePlayback() },
                onNext = { viewModel.next() },
                onPrevious = { viewModel.previous() },
                onToggleShuffle = { viewModel.toggleShuffle() },
                onCycleRepeat = { viewModel.cycleRepeat() },
                onSeek = { ms -> viewModel.seekTo(ms) },
                onToggleLike = { viewModel.currentApiTrack()?.let { viewModel.toggleLike(it) } },
                onPlayQueueIndex = { index -> viewModel.playQueueIndex(index) },
            )
        }
    }
}

private fun navigateTab(navController: NavHostController, route: String) {
    navController.navigate(route) {
        popUpTo(navController.graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

private fun normalizedEndpointFor(raw: String): String {
    val trimmed = raw.trim().trimEnd('/')
    if (trimmed.isBlank()) return ""
    return if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) trimmed else "http://$trimmed"
}

@Composable
private fun BottomBarWithMiniPlayer(
    activeRoute: String?,
    playback: PlaybackSnapshot,
    endpoint: String,
    token: String,
    isLiked: Boolean,
    activeImportCount: Int,
    onTabSelected: (String) -> Unit,
    onTogglePlay: () -> Unit,
    onToggleLike: () -> Unit,
    onExpand: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.navigationBars),
    ) {
        if (playback.currentTrack != null) {
            MiniPlayerBar(playback, endpoint, token, isLiked, onTogglePlay, onToggleLike, onExpand)
        }
        Row(
            Modifier
                .fillMaxWidth()
                .background(MekambColors.BackgroundAlt.copy(alpha = 0.96f))
                .padding(top = 8.dp, bottom = 10.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            tabs.forEach { tab ->
                val selected = tab.route == activeRoute
                Column(
                    Modifier
                        .weight(1f)
                        .clickable { onTabSelected(tab.route) },
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Box {
                        Icon(
                            tab.icon,
                            contentDescription = tab.label,
                            tint = if (selected) MekambColors.Accent else MekambColors.TextFaint,
                            modifier = Modifier.size(22.dp),
                        )
                        if (tab.route == Routes.Imports && activeImportCount > 0) {
                            Box(
                                Modifier
                                    .align(Alignment.TopEnd)
                                    .offset(x = 8.dp, y = (-3).dp)
                                    .size(14.dp)
                                    .clip(CircleShape)
                                    .background(MekambColors.Accent),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text(
                                    if (activeImportCount > 9) "9+" else "$activeImportCount",
                                    color = MekambColors.BackgroundAlt,
                                    fontSize = 8.sp,
                                    fontWeight = FontWeight.ExtraBold,
                                )
                            }
                        }
                    }
                    Text(
                        tab.label,
                        color = if (selected) MekambColors.Accent else MekambColors.TextFaint,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(top = 3.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun MiniPlayerBar(
    playback: PlaybackSnapshot,
    endpoint: String,
    token: String,
    isLiked: Boolean,
    onTogglePlay: () -> Unit,
    onToggleLike: () -> Unit,
    onExpand: () -> Unit,
) {
    val track = playback.currentTrack ?: return
    Column(
        Modifier
            .padding(horizontal = 10.dp)
            .padding(bottom = 6.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(MekambColors.SurfaceAlt.copy(alpha = 0.92f))
            .clickable { onExpand() },
    ) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 7.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            ArtworkImage(track.id, endpoint, token, size = 40.dp)
            Column(Modifier.weight(1f).padding(start = 10.dp)) {
                Text(track.title, color = MekambColors.TextPrimary, fontSize = 13.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(track.displayArtist, color = MekambColors.TextMuted, fontSize = 11.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 1.dp))
            }
            Icon(
                if (isLiked) Icons.Filled.Favorite else Icons.Filled.FavoriteBorder,
                contentDescription = "Like",
                tint = if (isLiked) MekambColors.Like else MekambColors.TextPrimary,
                modifier = Modifier.padding(6.dp).size(18.dp).clickable { onToggleLike() },
            )
            Icon(
                if (playback.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                contentDescription = "Play/Pause",
                tint = MekambColors.TextPrimary,
                modifier = Modifier
                    .padding(start = 4.dp)
                    .size(34.dp)
                    .clickable { onTogglePlay() },
            )
        }
        val fraction = if (playback.durationMs > 0) (playback.positionMs.toFloat() / playback.durationMs.toFloat()).coerceIn(0f, 1f) else 0f
        Box(Modifier.fillMaxWidth().height(2.5.dp).background(Color(0xFF222228))) {
            Box(Modifier.fillMaxWidth(fraction).height(2.5.dp).background(MekambColors.Accent))
        }
    }
}
