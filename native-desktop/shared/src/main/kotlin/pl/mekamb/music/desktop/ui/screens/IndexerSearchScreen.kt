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
import androidx.compose.material3.Button
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
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
import pl.mekamb.music.desktop.vm.Screen

@Composable
fun IndexerSearchScreen() {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()
    val settings by app.settings.state.collectAsState()

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
            val key = app.settings.state.value.prowlarrApiKey.ifBlank { null }
            runCatching { app.api.indexerSearch(q, key) }
                .onSuccess { results = it.items }
                .onFailure { error = it.message }
            loading = false
        }
    }

    fun importItem(item: SourceSearchItem) {
        val key = item.torrentId ?: item.name
        scope.launch {
            runCatching {
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
            }.onSuccess {
                importedIds = importedIds + key
                rowErrors = rowErrors - key
            }.onFailure {
                rowErrors = rowErrors + (key to (it.message ?: "Import failed"))
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        ScreenHeader(title = "Indexer search")

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            SearchField(
                value = query,
                onValueChange = { query = it },
                placeholder = "Search configured Prowlarr indexers",
                modifier = Modifier.fillMaxWidth().weight(1f),
            )
            Button(onClick = { search() }) { Text("Search") }
        }

        if (settings.prowlarrApiKey.isBlank()) {
            Surface(color = MekambColors.Chip, shape = RoundedCornerShape(8.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        "Optional: set your Prowlarr API key in Settings",
                        modifier = Modifier.weight(1f),
                        color = MekambColors.Muted,
                    )
                    TextButton(onClick = { app.navigate(Screen.Settings) }) { Text("Open Settings") }
                }
            }
        }

        when {
            loading -> LoadingState()
            error != null -> Text(error ?: "", color = MekambColors.Danger)
            !searched && results.isEmpty() ->
                EmptyState("Search for torrents", "Find music across configured indexer sources")
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
