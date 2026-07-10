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
import androidx.compose.material3.FilterChip
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.api.CatalogAddRequest
import pl.mekamb.music.desktop.api.CatalogItem
import pl.mekamb.music.desktop.api.CatalogRequestItem
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.EmptyState
import pl.mekamb.music.desktop.ui.components.LoadingState
import pl.mekamb.music.desktop.ui.components.ScreenHeader
import pl.mekamb.music.desktop.ui.components.SearchField
import pl.mekamb.music.desktop.ui.theme.MekambColors

@Composable
fun CatalogScreen() {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()

    var query by remember { mutableStateOf("") }
    var kind by remember { mutableStateOf("artist") }
    var results by remember { mutableStateOf<List<CatalogItem>>(emptyList()) }
    var requests by remember { mutableStateOf<List<CatalogRequestItem>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var searched by remember { mutableStateOf(false) }
    var addedIds by remember { mutableStateOf(setOf<String>()) }

    suspend fun loadRequests() {
        requests = runCatching { app.api.catalogRequests().items }.getOrDefault(emptyList())
    }

    LaunchedEffect(Unit) { loadRequests() }

    fun search() {
        val q = query.trim()
        if (q.isEmpty()) return
        scope.launch {
            loading = true
            error = null
            searched = true
            runCatching { app.api.catalogSearch(q, kind) }
                .onSuccess { results = it.items }
                .onFailure { error = it.message }
            loading = false
        }
    }

    fun add(item: CatalogItem) {
        scope.launch {
            runCatching { app.api.catalogAdd(item.toAddRequest()) }
                .onSuccess {
                    requests = it.items
                    addedIds = addedIds + item.id()
                }
                .onFailure { error = it.message }
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        ScreenHeader(title = "Add Music")

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = kind == "artist", onClick = { kind = "artist"; if (searched) search() }, label = { Text("Artists") })
            FilterChip(selected = kind == "album", onClick = { kind = "album"; if (searched) search() }, label = { Text("Albums") })
        }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            SearchField(
                value = query,
                onValueChange = { query = it },
                placeholder = "Search an artist or album to add to the catalog",
                modifier = Modifier.fillMaxWidth().weight(1f),
            )
            Button(onClick = { search() }) { Text("Search") }
        }

        when {
            loading -> LoadingState()
            error != null -> Text(error ?: "", color = MekambColors.Danger)
            !searched && results.isEmpty() ->
                EmptyState("Grow the shared catalog", "Search an artist or album; Lidarr fetches it and it appears in your library once imported.")
            searched && results.isEmpty() -> EmptyState("No results")
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(results) { item ->
                    CatalogResultRow(item = item, added = item.id() in addedIds, onAdd = { add(item) })
                }
                if (requests.isNotEmpty()) {
                    item {
                        Text("Recent requests", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 12.dp))
                    }
                    items(requests.take(12)) { req ->
                        Text("${req.title} — ${req.status.replaceFirstChar { it.uppercase() }}", color = MekambColors.Muted)
                    }
                }
            }
        }
    }
}

private fun CatalogItem.id(): String = "$kind:$foreignId"

private fun CatalogItem.toAddRequest(): CatalogAddRequest =
    CatalogAddRequest(
        kind = kind,
        foreignId = foreignId,
        title = title,
        artist = artist,
        artistForeignId = artistForeignId,
    )

@Composable
private fun CatalogResultRow(item: CatalogItem, added: Boolean, onAdd: () -> Unit) {
    Surface(color = MekambColors.Surface, shape = RoundedCornerShape(12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(item.title, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (item.subtitle.isNotBlank()) {
                    Text(item.subtitle, style = MaterialTheme.typography.bodySmall, color = MekambColors.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            Button(onClick = onAdd, enabled = !added) {
                Text(if (added) "Added" else "Add")
            }
        }
    }
}
