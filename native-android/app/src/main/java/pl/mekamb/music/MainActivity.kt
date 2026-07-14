package pl.mekamb.music

import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import pl.mekamb.music.ui.nav.MekambApp
import pl.mekamb.music.ui.theme.MekambTheme

/**
 * Single-Activity Compose host. All screen UI lives under `ui/`; this class only owns the Android
 * entry point, the one-time notification permission prompt, and starting the Compose tree.
 * Playback itself is the process-scoped [Playback] singleton (untouched by this rewrite) plus its
 * foreground [MediaPlaybackService] — both keep running independently of this Activity's lifecycle.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        Playback.init(this)
        requestNotificationPermissionIfNeeded()
        setContent {
            MekambTheme {
                MekambApp()
            }
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) !=
            android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 42)
        }
    }
}
