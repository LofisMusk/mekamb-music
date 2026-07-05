package pl.mekamb.music.desktop.ui

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import pl.mekamb.music.desktop.ui.theme.MekambTheme
import pl.mekamb.music.desktop.vm.AppViewModel

@Composable
fun App() {
    val app = remember { AppViewModel() }
    DisposableEffect(Unit) {
        onDispose { app.shutdown() }
    }
    CompositionLocalProvider(LocalApp provides app) {
        MekambTheme {
            AppShell()
        }
    }
}
