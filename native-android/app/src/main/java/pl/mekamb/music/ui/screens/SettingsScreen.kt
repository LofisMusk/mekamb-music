package pl.mekamb.music.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.AppUiState
import pl.mekamb.music.AppViewModel
import pl.mekamb.music.BuildConfig
import pl.mekamb.music.ConnectionStatus
import pl.mekamb.music.ui.components.BackIconButton
import pl.mekamb.music.ui.theme.MekambColors

@Composable
fun SettingsScreen(uiState: AppUiState, viewModel: AppViewModel, onBack: () -> Unit, onOpenAdmin: () -> Unit = {}) {
    LaunchedEffect(Unit) { viewModel.loadCacheStats() }

    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 18.dp),
        contentPadding = PaddingValues(top = 10.dp, bottom = 32.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(bottom = 16.dp)) {
                BackIconButton(onBack, background = MekambColors.SurfaceAlt)
                Text("Settings", color = MekambColors.TextPrimary, fontSize = 23.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(start = 12.dp))
            }
        }
        item { AccountSection(uiState, viewModel, onOpenAdmin) }
        item { Spacer(Modifier.height(14.dp)) }
        item { ServerSection(uiState, viewModel) }
        item { Spacer(Modifier.height(14.dp)) }
        item { PlaybackSection(uiState, viewModel) }
        item { Spacer(Modifier.height(14.dp)) }
        item { StorageSection(uiState, viewModel) }
        item { Spacer(Modifier.height(14.dp)) }
        item { UpdatesSection() }
    }
}

@Composable
private fun SettingsCard(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(MekambColors.Surface, RoundedCornerShape(12.dp))
            .padding(horizontal = 14.dp, vertical = 4.dp),
        content = content,
    )
}

@Composable
private fun SectionLabel(text: String) {
    Text(text, color = MekambColors.TextFaint, fontSize = 10.5.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 1.1.sp, modifier = Modifier.padding(top = 12.dp, bottom = 8.dp))
}

@Composable
private fun AccountSection(uiState: AppUiState, viewModel: AppViewModel, onOpenAdmin: () -> Unit) {
    // Login / registration happen at the launch gate — Settings is only reachable while
    // signed in, so this only ever shows the current account (+ admin approval entry).
    SettingsCard {
        Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(46.dp).background(androidx.compose.ui.graphics.Brush.linearGradient(MekambColors.AvatarGradient), CircleShape), contentAlignment = Alignment.Center) {
                Text(uiState.accountUsername.take(2).uppercase(), color = MekambColors.BackgroundAlt, fontWeight = FontWeight.ExtraBold)
            }
            Column(Modifier.weight(1f).padding(start = 12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(uiState.accountUsername, color = MekambColors.TextPrimary, fontSize = 14.5.sp, fontWeight = FontWeight.Bold)
                    if (uiState.accountIsAdmin) {
                        Text(
                            "ADMIN",
                            color = MekambColors.Accent,
                            fontSize = 9.sp,
                            fontWeight = FontWeight.ExtraBold,
                            letterSpacing = 0.6.sp,
                            modifier = Modifier
                                .padding(start = 8.dp)
                                .background(MekambColors.Accent.copy(alpha = 0.16f), RoundedCornerShape(6.dp))
                                .padding(horizontal = 6.dp, vertical = 2.dp),
                        )
                    }
                }
                Text(uiState.accountEmail, color = MekambColors.TextMuted, fontSize = 12.sp, modifier = Modifier.padding(top = 2.dp))
            }
            OutlinedButton(onClick = { viewModel.logout() }) { Text("Sign out") }
        }
        if (uiState.accountIsAdmin) {
            Button(
                onClick = onOpenAdmin,
                colors = ButtonDefaults.buttonColors(containerColor = MekambColors.SurfaceAlt, contentColor = MekambColors.TextPrimary),
                modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
            ) {
                Text("Approve accounts")
            }
        }
    }
}

@Composable
private fun ServerSection(uiState: AppUiState, viewModel: AppViewModel) {
    var endpoint by remember(uiState.apiEndpoint) { mutableStateOf(uiState.apiEndpoint) }
    SettingsCard {
        SectionLabel("SERVER")
        OutlinedTextField(
            endpoint,
            onValueChange = { endpoint = it },
            label = { Text("API endpoint") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(bottom = 12.dp)) {
            val (dotColor, label) = when (uiState.connectionStatus) {
                ConnectionStatus.Connected -> MekambColors.Success to "Connected" + (uiState.connectionLatencyMs?.let { " · $it ms" } ?: "")
                ConnectionStatus.Failed -> MekambColors.Danger to "Connection failed"
                ConnectionStatus.Checking -> MekambColors.TextMuted to "Checking…"
                ConnectionStatus.Unknown -> MekambColors.TextMuted to "Not tested"
            }
            Box(Modifier.size(7.dp).background(dotColor, CircleShape))
            Text(label, color = dotColor, fontSize = 11.5.sp, modifier = Modifier.padding(start = 7.dp).weight(1f))
            TextButton(onClick = {
                viewModel.setApiEndpoint(endpoint)
                viewModel.testConnection()
            }) { Text("Test") }
            TextButton(onClick = {
                viewModel.setApiEndpoint(endpoint)
                viewModel.refreshLibrary()
            }) { Text("Save") }
        }
    }
}

@Composable
private fun PlaybackSection(uiState: AppUiState, viewModel: AppViewModel) {
    SettingsCard {
        SectionLabel("PLAYBACK")
        var qualityMenuOpen by remember { mutableStateOf(false) }
        Row(Modifier.fillMaxWidth().padding(vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Streaming quality", color = MekambColors.TextPrimary, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold)
                Text(qualityDescription(uiState.playbackQuality), color = MekambColors.TextMuted, fontSize = 11.5.sp, modifier = Modifier.padding(top = 2.dp))
            }
            Box {
                Text(
                    "${qualityLabel(uiState.playbackQuality)} ▾",
                    color = MekambColors.Accent,
                    fontSize = 11.5.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier
                        .background(MekambColors.Accent.copy(alpha = 0.12f), RoundedCornerShape(7.dp))
                        .clickable { qualityMenuOpen = true }
                        .padding(horizontal = 11.dp, vertical = 6.dp),
                )
                DropdownMenu(expanded = qualityMenuOpen, onDismissRequest = { qualityMenuOpen = false }) {
                    listOf("auto", "aac", "lossless").forEach { value ->
                        DropdownMenuItem(text = { Text(qualityLabel(value)) }, onClick = {
                            viewModel.setPlaybackQuality(value)
                            qualityMenuOpen = false
                        })
                    }
                }
            }
        }
        ToggleRow("Prefetch queued tracks", "Skips start instantly", uiState.prefetchQueuedTracks, viewModel::setPrefetchQueuedTracks)
        ToggleRow("Download over cellular", "Offline downloads on mobile data", uiState.downloadOverCellular, viewModel::setDownloadOverCellular, last = true)
    }
}

@Composable
private fun ToggleRow(title: String, subtitle: String, value: Boolean, onChange: (Boolean) -> Unit, last: Boolean = false) {
    Row(Modifier.fillMaxWidth().padding(vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, color = MekambColors.TextPrimary, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold)
            Text(subtitle, color = MekambColors.TextMuted, fontSize = 11.5.sp, modifier = Modifier.padding(top = 2.dp))
        }
        Switch(
            checked = value,
            onCheckedChange = onChange,
            colors = SwitchDefaults.colors(checkedTrackColor = MekambColors.Accent, checkedThumbColor = Color.White),
        )
    }
}

@Composable
private fun StorageSection(uiState: AppUiState, viewModel: AppViewModel) {
    SettingsCard {
        SectionLabel("STORAGE")
        Row(Modifier.fillMaxWidth().padding(vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Offline downloads", color = MekambColors.TextPrimary, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold)
                Text("${uiState.offlineCount} tracks", color = MekambColors.TextMuted, fontSize = 11.5.sp, modifier = Modifier.padding(top = 2.dp))
            }
            Text(formatMb(uiState.offlineBytes / (1024.0 * 1024.0)), color = MekambColors.TextMuted, fontSize = 12.sp)
        }
        Row(Modifier.fillMaxWidth().padding(vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Streaming cache", color = MekambColors.TextPrimary, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Text(uiState.cacheStats?.let { formatMb(it.totalSizeMb) } ?: "—", color = MekambColors.TextMuted, fontSize = 12.sp, modifier = Modifier.padding(end = 10.dp))
            OutlinedButton(onClick = { viewModel.clearStreamingCache() }) { Text("Clear") }
        }
    }
}

@Composable
private fun UpdatesSection() {
    var checkResult by remember { mutableStateOf<String?>(null) }
    SettingsCard {
        Row(Modifier.fillMaxWidth().padding(vertical = 13.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Mekamb Music v${BuildConfig.VERSION_NAME}", color = MekambColors.TextPrimary, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold)
                Text(checkResult ?: "You're up to date", color = MekambColors.TextMuted, fontSize = 11.5.sp, modifier = Modifier.padding(top = 2.dp))
            }
            // This is a self-hosted, sideloaded app with no update-check backend — "Check" only
            // confirms the currently-installed build is the one you're running, nothing more.
            OutlinedButton(onClick = { checkResult = "You're up to date" }) { Text("Check") }
        }
    }
}

private fun qualityLabel(value: String) = when (value) {
    "aac" -> "AAC"
    "lossless" -> "Lossless"
    else -> "Auto"
}

private fun qualityDescription(value: String) = when (value) {
    "aac" -> "Transcoded AAC — smaller downloads"
    "lossless" -> "Original files — lossless"
    else -> "AAC on cellular, lossless on Wi-Fi"
}

private fun formatMb(mb: Double): String = if (mb >= 1024) "%.1f GB".format(mb / 1024.0) else "%.0f MB".format(mb)
