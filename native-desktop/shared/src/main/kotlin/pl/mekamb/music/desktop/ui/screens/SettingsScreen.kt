package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.BuildInfo
import pl.mekamb.music.desktop.api.LibrarySummaryResponse
import pl.mekamb.music.desktop.api.normalizeEndpoint
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.LoadingState
import pl.mekamb.music.desktop.ui.components.ScreenHeader
import pl.mekamb.music.desktop.ui.components.UpdateFlow
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.util.formatBytes
import pl.mekamb.music.desktop.util.formatDuration

@Composable
fun SettingsScreen() {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()
    val settings by app.settings.state.collectAsState()

    var endpoint by remember { mutableStateOf(settings.endpoint) }
    var token by remember { mutableStateOf(settings.apiToken) }
    var tokenVisible by remember { mutableStateOf(false) }
    var prowlarrKey by remember { mutableStateOf(settings.prowlarrApiKey) }
    var testResult by remember { mutableStateOf<Result<Unit>?>(null) }
    var confirmRemoveAll by remember { mutableStateOf(false) }
    var summary by remember { mutableStateOf<LibrarySummaryResponse?>(null) }

    LaunchedEffect(Unit) {
        summary = runCatching { app.api.librarySummary() }.getOrNull()
    }

    Column(
        modifier = Modifier
            .verticalScroll(rememberScrollState())
            .widthIn(max = 640.dp)
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        ScreenHeader(title = "Settings")

        SettingsSection(title = "Server") {
            OutlinedTextField(
                value = endpoint,
                onValueChange = { endpoint = it },
                label = { Text("Server endpoint") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            OutlinedTextField(
                value = token,
                onValueChange = { token = it },
                label = { Text("API token") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                visualTransformation = if (tokenVisible) VisualTransformation.None else PasswordVisualTransformation(),
                trailingIcon = {
                    IconButton(onClick = { tokenVisible = !tokenVisible }) {
                        Icon(
                            if (tokenVisible) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                            contentDescription = if (tokenVisible) "Hide token" else "Show token",
                        )
                    }
                },
            )
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(onClick = { scope.launch { testResult = app.testConnection(endpoint, token) } }) {
                    Text("Test connection")
                }
                testResult?.let {
                    Text(
                        if (it.isSuccess) "✓ Connected" else "✗ ${it.exceptionOrNull()?.message}",
                        color = if (it.isSuccess) MekambColors.Success else MekambColors.Danger,
                    )
                }
            }
            Button(
                onClick = {
                    app.settings.update { it.copy(endpoint = normalizeEndpoint(endpoint), apiToken = token) }
                    app.refreshLibrary()
                },
            ) { Text("Save") }
        }

        SettingsSection(title = "Search") {
            OutlinedTextField(
                value = prowlarrKey,
                onValueChange = { prowlarrKey = it },
                label = { Text("Prowlarr API key") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            Button(onClick = { app.settings.update { it.copy(prowlarrApiKey = prowlarrKey) } }) {
                Text("Save")
            }
        }

        SettingsSection(title = "Playback") {
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text("Autoplay similar tracks when queue ends", modifier = Modifier.weight(1f))
                Switch(
                    checked = settings.autoplaySimilar,
                    onCheckedChange = { checked -> app.settings.update { it.copy(autoplaySimilar = checked) } },
                )
            }
        }

        SettingsSection(title = "Offline downloads") {
            val offlineIds by app.downloads.offlineTrackIds.collectAsState()
            Text("${offlineIds.size} tracks · ${formatBytes(app.downloads.storageUsageBytes())}")
            Button(
                onClick = { confirmRemoveAll = true },
                colors = ButtonDefaults.buttonColors(containerColor = MekambColors.Danger),
            ) { Text("Remove all") }
        }

        SettingsSection(title = "Updates") {
            Text("Version: ${BuildInfo.APP_VERSION}")
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text("Check for updates on startup", modifier = Modifier.weight(1f))
                Switch(
                    checked = settings.checkUpdatesOnStartup,
                    onCheckedChange = { checked -> app.settings.update { it.copy(checkUpdatesOnStartup = checked) } },
                )
            }
            Button(onClick = { UpdateFlow.triggerManualCheck() }) { Text("Check for updates now") }
        }

        SettingsSection(title = "Library") {
            val current = summary
            if (current == null) {
                LoadingState()
            } else {
                Text("Tracks: ${current.trackCount}")
                Text("Albums: ${current.albumCount}")
                Text("Artists: ${current.artistCount}")
                Text("Playlists: ${current.playlistCount}")
                Text("Library size: ${formatBytes(current.librarySizeBytes)}")
                Text("Total duration: ${formatDuration(current.totalDurationSeconds)}")
            }
            Button(onClick = { app.refreshLibrary() }) { Text("Refresh library") }
        }
    }

    if (confirmRemoveAll) {
        AlertDialog(
            onDismissRequest = { confirmRemoveAll = false },
            title = { Text("Remove all downloads?") },
            text = { Text("This will delete every offline track from local storage.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        app.downloads.removeAllDownloads()
                        confirmRemoveAll = false
                    },
                ) { Text("Remove all", color = MekambColors.Danger) }
            },
            dismissButton = {
                TextButton(onClick = { confirmRemoveAll = false }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun SettingsSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column {
        Text(title, color = MekambColors.Accent, style = MaterialTheme.typography.labelLarge)
        Spacer(modifier = Modifier.height(8.dp))
        Surface(color = MekambColors.Elevated, shape = RoundedCornerShape(14.dp)) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                content = content,
            )
        }
    }
}
