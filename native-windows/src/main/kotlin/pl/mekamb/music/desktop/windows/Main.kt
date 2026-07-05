package pl.mekamb.music.desktop.windows

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import java.awt.Dimension
import pl.mekamb.music.desktop.BuildInfo
import pl.mekamb.music.desktop.ui.App

fun main() = application {
    Window(
        onCloseRequest = ::exitApplication,
        title = BuildInfo.APP_NAME,
        state = rememberWindowState(width = 1280.dp, height = 820.dp),
        icon = painterResource("logo.png"),
    ) {
        // The UI adapts down to this size (icon-only sidebar, no queue panel); below it
        // there just isn't room for a usable layout.
        LaunchedEffect(Unit) { window.minimumSize = Dimension(720, 480) }
        App()
    }
}
