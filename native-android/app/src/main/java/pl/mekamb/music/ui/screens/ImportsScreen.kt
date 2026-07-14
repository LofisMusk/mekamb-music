package pl.mekamb.music.ui.screens

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import pl.mekamb.music.AppUiState
import pl.mekamb.music.AppViewModel
import pl.mekamb.music.data.ImportRecord
import pl.mekamb.music.data.ImportStatus
import pl.mekamb.music.ui.components.ImportStatusChip
import pl.mekamb.music.ui.components.ScreenTitle
import pl.mekamb.music.ui.theme.MekambColors

@Composable
fun ImportsScreen(uiState: AppUiState, viewModel: AppViewModel) {
    LaunchedEffect(Unit) {
        while (isActive) {
            viewModel.loadImports()
            delay(4000)
        }
    }

    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 18.dp),
        contentPadding = PaddingValues(top = 10.dp, bottom = 24.dp),
    ) {
        item { ScreenTitle("Imports", Modifier.padding(bottom = 4.dp)) }
        item {
            Text(
                "Albums acquired through the catalog appear here as they ingest.",
                color = MekambColors.TextMuted,
                fontSize = 12.5.sp,
                modifier = Modifier.padding(bottom = 16.dp),
            )
        }
        if (uiState.imports.isEmpty()) {
            item { Text("No imports yet.", color = MekambColors.TextMuted, fontSize = 13.sp) }
        }
        items(uiState.imports, key = { it.id }) { record ->
            ImportRow(record, onCancel = { viewModel.cancelImport(record.id) }, onRetry = { viewModel.retryImport(record.id) }, modifier = Modifier.padding(bottom = 10.dp))
        }
    }
}

@Composable
private fun ImportRow(record: ImportRecord, onCancel: () -> Unit, onRetry: () -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier
            .fillMaxWidth()
            .background(MekambColors.Surface, RoundedCornerShape(10.dp))
            .padding(13.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(record.title, color = MekambColors.TextPrimary, fontSize = 13.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val quality = listOfNotNull(record.source, "via Lidarr").joinToString(" · ")
                Text(quality, color = MekambColors.TextMuted, fontSize = 11.sp, modifier = Modifier.padding(top = 2.dp))
            }
            ImportStatusChip(record.status, Modifier.padding(start = 8.dp))
        }
        if (record.status.isActive) {
            // The backend doesn't expose byte-level import progress on this endpoint, so we show
            // an indeterminate animated bar instead of fabricating a percentage.
            Box(Modifier.fillMaxWidth().padding(top = 9.dp)) {
                IndeterminateBar()
            }
            Text(stageLabel(record.status), color = MekambColors.TextMuted, fontSize = 11.sp, modifier = Modifier.padding(top = 6.dp))
        }
        if (record.status == ImportStatus.Failed && !record.errorMessage.isNullOrBlank()) {
            Text(record.errorMessage, color = MekambColors.Danger, fontSize = 11.5.sp, modifier = Modifier.padding(top = 8.dp))
        }
        if (record.status.isActive || record.status == ImportStatus.Failed) {
            Row(Modifier.padding(top = 8.dp)) {
                if (record.status.isActive) {
                    OutlinedButton(onClick = onCancel) { Text("Cancel", fontSize = 12.sp) }
                }
                if (record.status == ImportStatus.Failed) {
                    OutlinedButton(onClick = onRetry) { Text("Retry", fontSize = 12.sp) }
                }
            }
        }
    }
}

@Composable
private fun IndeterminateBar() {
    val transition = rememberInfiniteTransition(label = "import-bar")
    val position by transition.animateFloat(
        initialValue = -0.35f,
        targetValue = 1.05f,
        animationSpec = infiniteRepeatable(tween(1200, easing = LinearEasing)),
        label = "position",
    )
    BoxWithConstraints(
        Modifier
            .fillMaxWidth()
            .height(4.dp)
            .clip(RoundedCornerShape(2.dp))
            .background(MekambColors.BorderSubtle),
    ) {
        Box(
            Modifier
                .width(maxWidth * 0.35f)
                .height(4.dp)
                .offset(x = maxWidth * position)
                .background(MekambColors.Accent, RoundedCornerShape(2.dp)),
        )
    }
}

private fun stageLabel(status: ImportStatus): String = when (status) {
    ImportStatus.Downloading -> "Downloading from peers"
    ImportStatus.ReadyToImport -> "Validating & ingesting"
    else -> "Waiting for worker"
}
