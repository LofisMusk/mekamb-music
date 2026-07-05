package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.api.IndexerImportRequest
import pl.mekamb.music.desktop.api.SourceSearchItem
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.EmptyState
import pl.mekamb.music.desktop.ui.components.LoadingState
import pl.mekamb.music.desktop.ui.components.ScreenHeader
import pl.mekamb.music.desktop.ui.components.SearchField
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.util.formatBytes
import pl.mekamb.music.desktop.vm.Screen

@Composable
fun TorrentSearchScreen() {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()

    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<SourceSearchItem>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var searched by remember { mutableStateOf(false) }
    var importedIds by remember { mutableStateOf(setOf<String>()) }
    var rowErrors by remember { mutableStateOf(mapOf<String, String>()) }

    fun search() {
        val q = query.trim()
        if (q.isEmpty()) return
        scope.launch {
            loading = true
            error = null
            searched = true
            runCatching { app.api.unifiedSearch(q) }
                .onSuccess { results = it.items }
                .onFailure { error = it.message }
            loading = false
        }
    }

    fun importItem(item: SourceSearchItem) {
        val key = item.torrentId ?: item.name
        scope.launch {
            runCatching {
                when (item.source) {
                    "1337x" -> app.api.import1337x(item.torrentId!!)
                    "piratebay" -> app.api.importPirateBay(item.torrentId!!)
                    else -> {
                        if (item.magnetLink.isNullOrBlank() || item.infoHash.isNullOrBlank()) {
                            throw IllegalStateException("Missing magnet link or info hash for indexer import")
                        }
                        app.api.importIndexer(
                            IndexerImportRequest(
                                name = item.name,
                                torrentId = item.torrentId,
                                infoHash = item.infoHash,
                                magnetLink = item.magnetLink,
                                uploader = item.uploader,
                                sourceUrl = item.sourceUrl,
                            ),
                        )
                    }
                }
            }.onSuccess {
                importedIds = importedIds + key
                rowErrors = rowErrors - key
            }.onFailure {
                rowErrors = rowErrors + (key to (it.message ?: "Import failed"))
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        ScreenHeader(title = "Torrent search")

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            SearchField(
                value = query,
                onValueChange = { query = it },
                placeholder = "Search torrents by artist, album, or track",
                modifier = Modifier.fillMaxWidth().weight(1f),
            )
            Button(onClick = { search() }) { Text("Search") }
        }

        when {
            loading -> LoadingState()
            error != null -> Text(error ?: "", color = MekambColors.Danger)
            !searched && results.isEmpty() ->
                EmptyState("Search for torrents", "Find music across configured torrent sources")
            searched && results.isEmpty() -> EmptyState("No results")
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(results) { item ->
                    TorrentResultRow(
                        item = item,
                        imported = (item.torrentId ?: item.name) in importedIds,
                        rowError = rowErrors[item.torrentId ?: item.name],
                        onImport = { importItem(item) },
                        onViewImports = { app.navigate(Screen.Imports) },
                    )
                }
            }
        }
    }
}

@Composable
internal fun TorrentResultRow(
    item: SourceSearchItem,
    imported: Boolean,
    rowError: String?,
    onImport: () -> Unit,
    onViewImports: () -> Unit,
) {
    Surface(color = MekambColors.Surface, shape = RoundedCornerShape(12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    item.name,
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Surface(color = MekambColors.Chip, shape = RoundedCornerShape(4.dp)) {
                        Text(
                            item.source,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                        )
                    }
                    item.seeders?.let {
                        Text("▲ $it", style = MaterialTheme.typography.labelSmall, color = MekambColors.Success)
                    }
                    item.leechers?.let {
                        Text("▼ $it", style = MaterialTheme.typography.labelSmall, color = MekambColors.Muted)
                    }
                    Text(
                        item.size ?: formatBytes(item.sizeBytes),
                        style = MaterialTheme.typography.labelSmall,
                        color = MekambColors.Muted,
                    )
                    item.uploader?.let {
                        Text(it, style = MaterialTheme.typography.labelSmall, color = MekambColors.Muted)
                    }
                }
                rowError?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = MekambColors.Danger) }
            }
            if (imported) {
                Column(horizontalAlignment = androidx.compose.ui.Alignment.End) {
                    Text("Queued ✓", color = MekambColors.Success)
                    TextButton(onClick = onViewImports) { Text("View in Imports") }
                }
            } else {
                Button(onClick = onImport) { Text("Import") }
            }
        }
    }
}
