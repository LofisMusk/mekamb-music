package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.api.DownloadStatusResponse
import pl.mekamb.music.desktop.api.ImportRecord
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.EmptyState
import pl.mekamb.music.desktop.ui.components.ScreenHeader
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.util.formatBytes
import pl.mekamb.music.desktop.util.formatDuration

private val TERMINAL_STATUSES = setOf("complete", "failed", "cancelled", "imported")
private val ACTIVE_LIKE_STATUSES = setOf("pending", "downloading", "importing", "indexing")

@Composable
fun ImportsScreen() {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()

    var imports by remember { mutableStateOf<List<ImportRecord>>(emptyList()) }
    var statuses by remember { mutableStateOf<Map<String, DownloadStatusResponse>>(emptyMap()) }
    var refreshedLibraryFor by remember { mutableStateOf(setOf<String>()) }
    var loaded by remember { mutableStateOf(false) }

    suspend fun reload() {
        imports = runCatching { app.api.listImports(limit = 50).items }.getOrDefault(imports)
        loaded = true
    }

    LaunchedEffect(Unit) { reload() }

    LaunchedEffect(imports) {
        while (isActive) {
            val active = imports.filter { it.status !in TERMINAL_STATUSES }
            if (active.isNotEmpty()) {
                val fetched = active.take(10).map { rec ->
                    async { rec.id to runCatching { app.api.downloadStatus(rec.id) }.getOrNull() }
                }.awaitAll().mapNotNull { (id, s) -> s?.let { id to it } }.toMap()
                statuses = statuses + fetched
                fetched.forEach { (id, status) ->
                    if (status.importRecord.status in setOf("complete", "imported") && id !in refreshedLibraryFor) {
                        refreshedLibraryFor = refreshedLibraryFor + id
                        app.refreshLibrary()
                    }
                }
            }
            delay(1250)
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        ScreenHeader(
            title = "Imports",
            actions = {
                IconButton(onClick = { scope.launch { reload() } }) {
                    Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
                }
            },
        )

        if (loaded && imports.isEmpty()) {
            EmptyState("No imports yet")
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(imports, key = { it.id }) { record ->
                    ImportCard(
                        record = record,
                        status = statuses[record.id],
                        onCancel = { scope.launch { runCatching { app.api.cancelImport(record.id) }; reload() } },
                        onRetry = { scope.launch { runCatching { app.api.retryImport(record.id) }; reload() } },
                    )
                }
            }
        }
    }
}

@Composable
private fun ImportCard(
    record: ImportRecord,
    status: DownloadStatusResponse?,
    onCancel: () -> Unit,
    onRetry: () -> Unit,
) {
    val torrent = status?.torrent
    val title = torrent?.name ?: record.torrentId ?: record.id
    val effectiveStatus = status?.importRecord?.status ?: record.status
    val chipColor = when (effectiveStatus) {
        "complete", "imported" -> MekambColors.Success
        "failed" -> MekambColors.Danger
        else -> MekambColors.Accent
    }

    Surface(color = MekambColors.Surface, shape = RoundedCornerShape(12.dp)) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(title, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
                Surface(color = chipColor.copy(alpha = 0.2f), shape = RoundedCornerShape(4.dp)) {
                    Text(
                        effectiveStatus,
                        style = MaterialTheme.typography.labelSmall,
                        color = chipColor,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                    )
                }
            }

            val progress = torrent?.progress
            if (torrent != null && progress != null) {
                LinearProgressIndicator(
                    progress = { progress.toFloat() },
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "${formatBytes(torrent.downloadedBytes)} / ${formatBytes(torrent.sizeBytes)} · " +
                        "${formatBytes(torrent.downloadSpeedBytes)}/s · ETA ${formatDuration(torrent.etaSeconds?.toDouble())}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MekambColors.Muted,
                )
            }

            record.errorMessage?.let { Text(it, color = MekambColors.Danger) }

            val isActive = effectiveStatus in ACTIVE_LIKE_STATUSES
            if (isActive || effectiveStatus == "failed") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (isActive) {
                        Button(onClick = onCancel) { Text("Cancel") }
                    }
                    if (effectiveStatus == "failed") {
                        Button(onClick = onRetry) { Text("Retry") }
                    }
                }
            }
        }
    }
}
