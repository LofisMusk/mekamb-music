package pl.mekamb.music.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.sp

/**
 * Exact palette from the "Mekamb Mobile" design handoff (Mekamb Mobile.dc.html). The app is
 * dark-only by design (near-black background + blue accent), so [MekambTheme] always applies this
 * palette regardless of the system light/dark setting.
 */
object MekambColors {
    val Background = Color(0xFF101014)
    val BackgroundAlt = Color(0xFF0B0B0D)
    val Surface = Color(0xFF131317)
    val SurfaceAlt = Color(0xFF1A1A1F)
    val SurfaceElevated = Color(0xFF17171B)
    val BorderSubtle = Color(0xFF1E1E24)
    val Border = Color(0xFF26262E)
    val BorderStrong = Color(0xFF2E2E36)
    val TextPrimary = Color(0xFFF2F4F8)
    val TextMuted = Color(0xFF9BA1AC)
    val TextFaint = Color(0xFF6E7480)
    val Accent = Color(0xFF5AA9FF)
    val AccentDeep = Color(0xFF2F7FE0)
    val Link = Color(0xFF8CC4FF)
    val Like = Color(0xFFFF6B9D)
    val Success = Color(0xFF4CD984)
    val Danger = Color(0xFFF46363)

    /** Tint used for the accent gradient behind avatars / like-fills (top-right → bottom-left). */
    val AvatarGradient = listOf(AccentDeep, Accent)
    val LikedHeroGradient = listOf(AccentDeep, Color(0xFF7B5BD6), Like)
}

private val MekambColorScheme = darkColorScheme(
    primary = MekambColors.Accent,
    onPrimary = MekambColors.BackgroundAlt,
    secondary = MekambColors.Accent,
    background = MekambColors.Background,
    onBackground = MekambColors.TextPrimary,
    surface = MekambColors.Surface,
    onSurface = MekambColors.TextPrimary,
    surfaceVariant = MekambColors.SurfaceAlt,
    onSurfaceVariant = MekambColors.TextMuted,
    outline = MekambColors.Border,
    error = MekambColors.Danger,
    onError = MekambColors.TextPrimary,
)

val TitleTextStyle = TextStyle(fontSize = 23.sp, letterSpacing = (-0.3).sp)

@Composable
fun MekambTheme(content: @Composable () -> Unit) {
    // Deliberately not derived from the system light/dark setting: the design is dark-only.
    MaterialTheme(
        colorScheme = MekambColorScheme,
        content = content,
    )
}
