package pl.mekamb.music.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.AppUiState
import pl.mekamb.music.AppViewModel
import pl.mekamb.music.data.CatalogItem
import pl.mekamb.music.data.CatalogRequestItem
import pl.mekamb.music.ui.components.ScreenTitle
import pl.mekamb.music.ui.theme.MekambColors

@Composable
fun AddMusicScreen(uiState: AppUiState, viewModel: AppViewModel) {
    var query by remember { mutableStateOf("") }

    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 18.dp),
        contentPadding = PaddingValues(top = 10.dp, bottom = 24.dp),
    ) {
        item { ScreenTitle("Add Music", Modifier.padding(bottom = 14.dp)) }
        item {
            Row(Modifier.padding(bottom = 10.dp)) {
                listOf("artist" to "Artists", "album" to "Albums").forEach { (kind, label) ->
                    val active = uiState.catalogKind == kind
                    Text(
                        label,
                        color = if (active) MekambColors.BackgroundAlt else MekambColors.TextMuted,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier
                            .weight(1f)
                            .padding(horizontal = 3.dp)
                            .background(if (active) MekambColors.Accent else MekambColors.SurfaceAlt, RoundedCornerShape(10.dp))
                            .clickable {
                                viewModel.setCatalogKind(kind)
                                if (query.isNotBlank()) viewModel.searchCatalog(query)
                            }
                            .padding(vertical = 9.dp),
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    )
                }
            }
        }
        item {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                label = { Text(if (uiState.catalogKind == "artist") "Add an artist…" else "Add an album…") },
                singleLine = true,
                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = androidx.compose.foundation.text.KeyboardActions(onSearch = { viewModel.searchCatalog(query) }),
                modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
            )
        }
        if (query.isBlank()) {
            item {
                Text(
                    "Search an artist or album; Lidarr fetches it into the shared catalog and it appears in your library once imported.",
                    color = MekambColors.TextMuted,
                    fontSize = 12.5.sp,
                )
            }
        } else {
            items(uiState.catalogItems, key = { it.id }) { item ->
                CatalogRow(item, added = uiState.addedCatalogIds.contains(item.id), onAdd = { viewModel.addToCatalog(item) }, modifier = Modifier.padding(bottom = 8.dp))
            }
        }
        if (uiState.catalogRequests.isNotEmpty()) {
            item {
                Text("Recent requests", color = MekambColors.TextPrimary, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(top = 14.dp, bottom = 8.dp))
            }
            items(uiState.catalogRequests.take(12), key = { it.id }) { request ->
                RequestRow(request, modifier = Modifier.padding(bottom = 6.dp))
            }
        }
    }
}

@Composable
private fun CatalogRow(item: CatalogItem, added: Boolean, onAdd: () -> Unit, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().background(MekambColors.Surface, RoundedCornerShape(12.dp)).padding(14.dp)) {
        Text(item.title, color = MekambColors.TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
        if (item.subtitle.isNotBlank()) {
            Text(item.subtitle, color = MekambColors.TextMuted, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp))
        }
        Button(
            onClick = { if (!added) onAdd() },
            enabled = !added,
            colors = ButtonDefaults.buttonColors(containerColor = MekambColors.Accent, contentColor = MekambColors.BackgroundAlt),
            modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        ) {
            Text(if (added) "Added" else "Add")
        }
    }
}

@Composable
private fun RequestRow(request: CatalogRequestItem, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth().background(MekambColors.Surface, RoundedCornerShape(10.dp)).padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(request.title, color = MekambColors.TextPrimary, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(request.status.replaceFirstChar { it.uppercase() }, color = MekambColors.TextMuted, fontSize = 12.sp)
    }
}
