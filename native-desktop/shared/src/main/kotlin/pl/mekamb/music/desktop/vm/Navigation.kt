package pl.mekamb.music.desktop.vm

/** Top-level destinations shown in the sidebar. */
sealed interface Screen {
    data object Home : Screen
    data object Library : Screen
    data object Albums : Screen
    data class AlbumDetail(val albumTitle: String, val artist: String?) : Screen
    data object Playlists : Screen
    data class PlaylistDetail(val playlistId: String) : Screen
    data object Liked : Screen
    data object Catalog : Screen
    data object Libraries : Screen
    data class LibraryDetail(val libraryId: String) : Screen
    data object Imports : Screen
    data object Settings : Screen
}
