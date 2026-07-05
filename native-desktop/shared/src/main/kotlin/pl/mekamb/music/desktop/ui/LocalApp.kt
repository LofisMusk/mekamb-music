package pl.mekamb.music.desktop.ui

import androidx.compose.runtime.staticCompositionLocalOf
import pl.mekamb.music.desktop.vm.AppViewModel

/** Provides the single [AppViewModel] to the whole composition tree. */
val LocalApp = staticCompositionLocalOf<AppViewModel> {
    error("AppViewModel not provided")
}
