package pl.mekamb.music.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.AppViewModel
import pl.mekamb.music.data.AdminUser
import pl.mekamb.music.ui.components.BackIconButton
import pl.mekamb.music.ui.theme.MekambColors

/**
 * Admin-only panel to review pending signups and approve/reject them, plus the approved roster.
 * Backed by the `/admin/users` endpoints (admin-scoped) via [AppViewModel.loadAdminUsers].
 */
@Composable
fun AdminApprovalScreen(viewModel: AppViewModel, onBack: () -> Unit) {
    var pending by remember { mutableStateOf<List<AdminUser>>(emptyList()) }
    var approved by remember { mutableStateOf<List<AdminUser>>(emptyList()) }

    fun reload() = viewModel.loadAdminUsers { p, a -> pending = p; approved = a }
    LaunchedEffect(Unit) { reload() }

    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 18.dp),
        contentPadding = PaddingValues(top = 10.dp, bottom = 32.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(bottom = 16.dp)) {
                BackIconButton(onBack, background = MekambColors.SurfaceAlt)
                Text("Accounts", color = MekambColors.TextPrimary, fontSize = 23.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(start = 12.dp))
            }
        }

        item {
            Text("PENDING APPROVAL", color = MekambColors.TextFaint, fontSize = 10.5.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 1.1.sp, modifier = Modifier.padding(vertical = 8.dp))
        }
        if (pending.isEmpty()) {
            item {
                Text("No accounts awaiting approval.", color = MekambColors.TextMuted, fontSize = 13.sp, modifier = Modifier.padding(vertical = 4.dp))
            }
        } else {
            items(pending) { user ->
                PendingRow(user, onApprove = { viewModel.setUserApproval(user.id, true) { reload() } }, onReject = { viewModel.setUserApproval(user.id, false) { reload() } })
            }
        }

        if (approved.isNotEmpty()) {
            item {
                Text("APPROVED", color = MekambColors.TextFaint, fontSize = 10.5.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 1.1.sp, modifier = Modifier.padding(top = 18.dp, bottom = 8.dp))
            }
            items(approved) { user ->
                Column(Modifier.fillMaxWidth().background(MekambColors.Surface, RoundedCornerShape(10.dp)).padding(horizontal = 14.dp, vertical = 10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(user.username, color = MekambColors.TextPrimary, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                        if (user.isAdmin) {
                            Text("admin", color = MekambColors.Accent, fontSize = 10.sp, modifier = Modifier.padding(start = 8.dp))
                        }
                    }
                    Text(user.email, color = MekambColors.TextMuted, fontSize = 12.sp, modifier = Modifier.padding(top = 2.dp))
                }
                Spacer(Modifier.height(8.dp))
            }
        }
    }
}

@Composable
private fun PendingRow(user: AdminUser, onApprove: () -> Unit, onReject: () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(MekambColors.Surface, RoundedCornerShape(10.dp))
            .padding(14.dp),
    ) {
        Text(user.username, color = MekambColors.TextPrimary, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        Text(user.email, color = MekambColors.TextMuted, fontSize = 12.sp, modifier = Modifier.padding(top = 2.dp))
        Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(
                onClick = onApprove,
                colors = ButtonDefaults.buttonColors(containerColor = MekambColors.Accent, contentColor = MekambColors.BackgroundAlt),
                modifier = Modifier.weight(1f),
            ) { Text("Approve", fontWeight = FontWeight.Bold) }
            OutlinedButton(onClick = onReject, modifier = Modifier.weight(1f)) { Text("Reject", color = MekambColors.Danger) }
        }
    }
    Spacer(Modifier.height(8.dp))
}
