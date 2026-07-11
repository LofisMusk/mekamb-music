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
import pl.mekamb.music.desktop.api.ApiException
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
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(onClick = { scope.launch { testResult = app.testConnection(endpoint, settings.apiToken) } }) {
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
                    app.settings.update { it.copy(endpoint = normalizeEndpoint(endpoint)) }
                    app.refreshLibrary()
                },
            ) { Text("Save") }
        }

        SettingsSection(title = "Account") {
            AccountSection()
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

private enum class AuthMode(val label: String) {
    Login("Log in"),
    Migrate("Migrate token"),
    Register("Sign up"),
}

@Composable
private fun ColumnScope.AccountSection() {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()
    val settings by app.settings.state.collectAsState()

    if (settings.accountUsername.isNotBlank()) {
        Text("Signed in as ${settings.accountUsername}")
        Text(settings.accountEmail, style = MaterialTheme.typography.bodySmall)
        Button(
            onClick = { app.logout() },
            colors = ButtonDefaults.buttonColors(containerColor = MekambColors.Danger),
        ) { Text("Log out") }
        return
    }

    val hasLegacyToken = settings.apiToken.isNotBlank()
    var mode by remember { mutableStateOf(if (hasLegacyToken) AuthMode.Migrate else AuthMode.Login) }
    var identifier by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var passwordVisible by remember { mutableStateOf(false) }
    var legacyToken by remember { mutableStateOf(settings.apiToken) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<Pair<String, Boolean>?>(null) }

    if (hasLegacyToken) {
        Text(
            "This app is still using a legacy API token. Migrate it to an account: pick an " +
                "email, username and password — your library carries over and the old token " +
                "stops working everywhere.",
            style = MaterialTheme.typography.bodySmall,
        )
    }

    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        AuthMode.values().forEach { candidate ->
            TextButton(onClick = { mode = candidate; message = null }) {
                Text(
                    candidate.label,
                    color = if (mode == candidate) MekambColors.Accent
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }

    when (mode) {
        AuthMode.Login -> {
            OutlinedTextField(
                value = identifier,
                onValueChange = { identifier = it },
                label = { Text("Email or username") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
        }
        AuthMode.Migrate -> {
            OutlinedTextField(
                value = legacyToken,
                onValueChange = { legacyToken = it },
                label = { Text("Legacy API token") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            OutlinedTextField(
                value = email,
                onValueChange = { email = it },
                label = { Text("Email") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                label = { Text("Username") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
        }
        AuthMode.Register -> {
            OutlinedTextField(
                value = email,
                onValueChange = { email = it },
                label = { Text("Email") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                label = { Text("Username") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
        }
    }

    OutlinedTextField(
        value = password,
        onValueChange = { password = it },
        label = { Text("Password") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
        visualTransformation = if (passwordVisible) VisualTransformation.None else PasswordVisualTransformation(),
        trailingIcon = {
            IconButton(onClick = { passwordVisible = !passwordVisible }) {
                Icon(
                    if (passwordVisible) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                    contentDescription = if (passwordVisible) "Hide password" else "Show password",
                )
            }
        },
    )

    Button(
        enabled = !busy,
        onClick = {
            busy = true
            message = null
            scope.launch {
                val result = when (mode) {
                    AuthMode.Login ->
                        app.login(identifier, password).map { "Signed in as ${it.username}" }
                    AuthMode.Migrate ->
                        app.claimLegacyToken(email, username, password, legacyToken)
                            .map { "Token migrated — signed in as ${it.username}" }
                    AuthMode.Register ->
                        app.registerAccount(email, username, password).map { it.message }
                }
                busy = false
                message = result.fold(
                    onSuccess = { it to false },
                    onFailure = { failure ->
                        val text = if (failure is ApiException) failure.userMessage()
                        else failure.message ?: "Request failed"
                        text to true
                    },
                )
            }
        },
    ) {
        Text(
            when {
                busy -> "Working…"
                mode == AuthMode.Login -> "Log in"
                mode == AuthMode.Migrate -> "Migrate & sign in"
                else -> "Create account"
            }
        )
    }

    message?.let { (text, isError) ->
        Text(text, color = if (isError) MekambColors.Danger else MekambColors.Success)
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
