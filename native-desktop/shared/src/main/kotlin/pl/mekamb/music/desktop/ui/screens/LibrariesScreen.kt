package pl.mekamb.music.desktop.ui.screens

import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import pl.mekamb.music.desktop.ui.LocalApp
import pl.mekamb.music.desktop.ui.components.EmptyState
import pl.mekamb.music.desktop.ui.components.ScreenHeader
import pl.mekamb.music.desktop.ui.theme.MekambColors
import pl.mekamb.music.desktop.vm.Screen

@Composable
fun LibrariesScreen() {
    val app = LocalApp.current
    val libraries by app.libraries.collectAsState()
    val scope = rememberCoroutineScope()
    var showCreate by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        ScreenHeader(
            title = "My Libraries",
            actions = {
                Button(onClick = { showCreate = true }) { Text("New library") }
            },
        )

        if (libraries.isEmpty()) {
            EmptyState("No libraries yet", "Create a library, then add tracks from the shared catalog.")
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                items(libraries) { library ->
                    Surface(
                        color = MekambColors.Surface,
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth().clickable { app.navigate(Screen.LibraryDetail(library.id)) },
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(library.name, style = MaterialTheme.typography.bodyLarge)
                                Text("${library.trackCount} tracks", style = MaterialTheme.typography.bodySmall, color = MekambColors.Muted)
                            }
                            IconButton(onClick = {
                                scope.launch {
                                    runCatching { app.api.deleteLibrary(library.id) }
                                    app.loadLibraries()
                                }
                            }) {
                                Icon(Icons.Filled.Delete, contentDescription = "Delete")
                            }
                        }
                    }
                }
            }
        }
    }

    if (showCreate) {
        var name by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { showCreate = false },
            title = { Text("New library") },
            text = {
                OutlinedTextField(value = name, onValueChange = { name = it }, singleLine = true)
            },
            confirmButton = {
                TextButton(onClick = {
                    val trimmed = name.trim()
                    showCreate = false
                    if (trimmed.isNotEmpty()) {
                        scope.launch {
                            runCatching { app.api.createLibrary(trimmed) }
                            app.loadLibraries()
                        }
                    }
                }) { Text("Create") }
            },
            dismissButton = { TextButton(onClick = { showCreate = false }) { Text("Cancel") } },
        )
    }
}
