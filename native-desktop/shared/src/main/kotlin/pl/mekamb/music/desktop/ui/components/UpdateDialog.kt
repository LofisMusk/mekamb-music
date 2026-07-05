package pl.mekamb.music.desktop.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.BuildInfo
import pl.mekamb.music.desktop.api.buildHttpClient
import pl.mekamb.music.desktop.data.AppDirs
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.updater.AvailableUpdate
import pl.mekamb.music.desktop.updater.UpdateChecker
import pl.mekamb.music.desktop.updater.UpdateInstaller

/** Lets other screens (e.g. Settings) trigger a manual update check. */
object UpdateFlow {
    private val _manualTrigger = MutableStateFlow(0)
    fun triggerManualCheck() {
        _manualTrigger.value++
    }
    internal val manualTrigger: StateFlow<Int> = _manualTrigger
}

/**
 * Owns the whole update lifecycle: startup check, manual check, download progress, install.
 * Renders as overlay dialogs only when there is something to show.
 */
@Composable
fun UpdateFlowHost() {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()
    val checker = remember { UpdateChecker(buildHttpClient()) }

    var available by remember { mutableStateOf<AvailableUpdate?>(null) }
    var checking by remember { mutableStateOf(false) }
    var manualCheckMessage by remember { mutableStateOf<String?>(null) }
    var downloadProgress by remember { mutableStateOf<Float?>(null) }
    var installMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        val settings = app.settings.state.value
        if (settings.checkUpdatesOnStartup && settings.endpoint.isNotBlank()) {
            runCatching { checker.checkForUpdate(BuildInfo.APP_VERSION) }.getOrNull()?.let {
                if (it.version != app.settings.state.value.skippedUpdateVersion) available = it
            }
        }
    }

    LaunchedEffect(Unit) {
        UpdateFlow.manualTrigger.drop(1).collect { trigger ->
            if (trigger <= 0) return@collect
            checking = true
            manualCheckMessage = null
            val result = runCatching { checker.checkForUpdate(BuildInfo.APP_VERSION) }
            checking = false
            result.fold(
                onSuccess = { update ->
                    if (update != null) available = update
                    else manualCheckMessage = "You are up to date (v${BuildInfo.APP_VERSION})"
                },
                onFailure = { failure ->
                    manualCheckMessage = "Update check failed: ${failure.message}"
                },
            )
        }
    }

    val update = available
    if (update != null) {
        AlertDialog(
            onDismissRequest = {},
            title = { Text("Update available: v${update.version}") },
            text = {
                Column {
                    Text(
                        text = update.notes ?: "No release notes.",
                        modifier = Modifier.heightIn(max = 240.dp).verticalScroll(rememberScrollState()),
                        color = MekambColors.Text,
                    )
                    val progress = downloadProgress
                    if (progress != null) {
                        LinearProgressIndicator(
                            progress = { progress },
                            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                            color = MekambColors.Accent,
                        )
                    }
                    installMessage?.let { message ->
                        val isError = message.contains("failed", ignoreCase = true) ||
                            message.contains("mismatch", ignoreCase = true)
                        Text(
                            text = message,
                            color = if (isError) MekambColors.Danger else MekambColors.Success,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.padding(top = 8.dp),
                        )
                    }
                }
            },
            confirmButton = {
                Button(onClick = {
                    scope.launch {
                        downloadProgress = 0f
                        val file = checker.downloadUpdate(
                            update,
                            AppDirs.cacheDir.resolve("updates"),
                        ) { progress -> downloadProgress = progress }
                        val result = UpdateInstaller.install(file)
                        installMessage = result.getOrElse { "Install failed: ${it.message}" }
                        if (result.isSuccess) available = null
                    }
                }) {
                    Text("Install now")
                }
            },
            dismissButton = {
                Row {
                    TextButton(onClick = { available = null }) { Text("Later") }
                    TextButton(onClick = {
                        app.settings.update { it.copy(skippedUpdateVersion = update.version) }
                        available = null
                    }) {
                        Text("Skip this version")
                    }
                }
            },
        )
    } else if (manualCheckMessage != null) {
        AlertDialog(
            onDismissRequest = { manualCheckMessage = null },
            confirmButton = {
                TextButton(onClick = { manualCheckMessage = null }) { Text("OK") }
            },
            text = { Text(manualCheckMessage!!) },
        )
    }
}
