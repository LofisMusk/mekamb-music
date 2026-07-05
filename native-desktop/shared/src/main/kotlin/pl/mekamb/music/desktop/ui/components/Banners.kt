package pl.mekamb.music.desktop.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.vm.ConnectionState
import pl.mekamb.music.desktop.vm.Screen

/** Full-width banner reflecting the current backend connection state; renders nothing when connected. */
@Composable
fun ConnectionBanner() {
    val app = LocalApp.current
    when (val state = app.connectionState.collectAsState().value) {
        is ConnectionState.Error -> Surface(
            modifier = Modifier.fillMaxWidth(),
            color = MekambColors.Danger.copy(alpha = 0.15f),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Icon(imageVector = Icons.Filled.ErrorOutline, contentDescription = null, tint = MekambColors.Danger)
                Text(
                    text = state.message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MekambColors.Text,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = { app.refreshLibrary() }) {
                    Text("Retry", color = MekambColors.Accent)
                }
            }
        }

        ConnectionState.Unconfigured -> Surface(
            modifier = Modifier.fillMaxWidth(),
            color = MekambColors.Chip,
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Icon(imageVector = Icons.Filled.Info, contentDescription = null, tint = MekambColors.Muted)
                Text(
                    text = "Configure your server in Settings",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MekambColors.Text,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = { app.navigate(Screen.Settings) }) {
                    Text("Open Settings", color = MekambColors.Accent)
                }
            }
        }

        else -> Unit
    }
}
