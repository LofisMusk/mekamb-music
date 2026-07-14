package pl.mekamb.music.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.ui.theme.MekambColors

@Composable
fun ProfileMenuOverlay(
    username: String,
    email: String,
    onDismiss: () -> Unit,
    onOpenSettings: () -> Unit,
    onLogout: () -> Unit,
) {
    Box(
        Modifier
            .fillMaxSize()
            .background(Color(0x73050508))
            .clickable(onClick = onDismiss),
    ) {
        Column(
            Modifier
                .align(Alignment.TopEnd)
                .statusBarsPadding()
                .padding(top = 40.dp, end = 16.dp)
                .width(230.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(MekambColors.SurfaceAlt)
                .clickable(enabled = false) {}
                .padding(6.dp),
        ) {
            Row(Modifier.fillMaxWidth().padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.size(38.dp).background(Brush.linearGradient(MekambColors.AvatarGradient), CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(initialsFor(username), color = MekambColors.BackgroundAlt, fontSize = 12.sp, fontWeight = FontWeight.ExtraBold)
                }
                Column(Modifier.padding(start = 10.dp)) {
                    Text(username.ifBlank { "Not signed in" }, color = MekambColors.TextPrimary, fontSize = 13.5.sp, fontWeight = FontWeight.Bold)
                    Text(email, color = MekambColors.TextMuted, fontSize = 11.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            Box(Modifier.fillMaxWidth().height(1.dp).background(MekambColors.BorderStrong).padding(horizontal = 4.dp))
            MenuRow(Icons.Filled.Settings, "Settings", MekambColors.TextPrimary, onClick = onOpenSettings)
            MenuRow(Icons.Filled.AccountCircle, "Account", MekambColors.TextPrimary, onClick = {})
            Spacer(Modifier.height(6.dp))
            Box(Modifier.fillMaxWidth().height(1.dp).background(MekambColors.BorderStrong))
            Spacer(Modifier.height(6.dp))
            MenuRow(Icons.AutoMirrored.Filled.Logout, "Log out", MekambColors.Danger, onClick = onLogout)
        }
    }
}

@Composable
private fun MenuRow(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, color: Color, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = MekambColors.TextMuted, modifier = Modifier.size(16.dp))
        Text(label, color = color, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 11.dp))
    }
}

private fun initialsFor(name: String): String {
    val parts = name.trim().split(Regex("\\s+")).filter { it.isNotBlank() }
    if (parts.isEmpty()) return "?"
    return if (parts.size == 1) parts[0].take(2).uppercase() else (parts[0].take(1) + parts[1].take(1)).uppercase()
}
