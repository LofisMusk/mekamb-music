package pl.mekamb.music.desktop.ui.theme

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush

private val MekambDarkColorScheme = darkColorScheme(
    primary = MekambColors.Accent,
    onPrimary = MekambColors.BackgroundBottom,
    primaryContainer = MekambColors.AccentDeep,
    onPrimaryContainer = MekambColors.Text,
    secondary = MekambColors.Accent,
    onSecondary = MekambColors.BackgroundBottom,
    secondaryContainer = MekambColors.Chip,
    onSecondaryContainer = MekambColors.Text,
    background = MekambColors.BackgroundTop,
    onBackground = MekambColors.Text,
    surface = MekambColors.Surface,
    onSurface = MekambColors.Text,
    surfaceVariant = MekambColors.Elevated,
    onSurfaceVariant = MekambColors.Muted,
    surfaceContainerHigh = MekambColors.Elevated,
    surfaceContainerHighest = MekambColors.Chip,
    outline = MekambColors.Stroke,
    outlineVariant = MekambColors.Stroke,
    error = MekambColors.Danger,
    onError = MekambColors.Text,
)

@Composable
fun MekambTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = MekambDarkColorScheme) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        listOf(MekambColors.BackgroundTop, MekambColors.BackgroundBottom)
                    )
                )
        ) {
            content()
        }
    }
}
