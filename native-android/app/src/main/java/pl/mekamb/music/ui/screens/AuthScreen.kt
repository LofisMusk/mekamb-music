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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pl.mekamb.music.AppUiState
import pl.mekamb.music.AppViewModel
import pl.mekamb.music.ConnectionStatus
import pl.mekamb.music.ui.theme.MekambColors

/**
 * Launch gate shown until an account session exists (`AppUiState.hasSession`). Collects the server
 * URL (onboarding), then logs in or registers. Registration lands the account `pending` — the user
 * is told an admin must approve them before they can log in.
 */
@Composable
fun AuthScreen(uiState: AppUiState, viewModel: AppViewModel) {
    var mode by remember { mutableStateOf("login") } // "login" | "register"
    var identifier by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var endpoint by remember(uiState.apiEndpoint) { mutableStateOf(uiState.apiEndpoint) }
    var showServer by remember { mutableStateOf(uiState.apiEndpoint.isBlank()) }

    LaunchedEffect(Unit) { if (uiState.apiEndpoint.isNotBlank()) viewModel.testConnection() }

    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(Color0E1420, MekambColors.BackgroundAlt))),
        contentAlignment = Alignment.TopCenter,
    ) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .widthIn(max = 460.dp)
                .padding(horizontal = 24.dp)
                .padding(top = 64.dp, bottom = 40.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // ── Branding ──
            Box(
                Modifier
                    .size(76.dp)
                    .background(Brush.linearGradient(MekambColors.AvatarGradient), RoundedCornerShape(22.dp)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Filled.MusicNote, contentDescription = null, tint = Color.White, modifier = Modifier.size(36.dp))
            }
            Spacer(Modifier.height(14.dp))
            Text("Mekamb Music", color = MekambColors.TextPrimary, fontSize = 26.sp, fontWeight = FontWeight.ExtraBold)
            Text(
                if (mode == "login") "Sign in to your account" else "Request an account",
                color = MekambColors.TextMuted,
                fontSize = 14.sp,
                modifier = Modifier.padding(top = 4.dp),
            )
            Spacer(Modifier.height(24.dp))

            // ── Server (onboarding) ──
            Column(
                Modifier
                    .fillMaxWidth()
                    .background(MekambColors.Surface, RoundedCornerShape(14.dp))
                    .padding(14.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val (dot, label) = when (uiState.connectionStatus) {
                        ConnectionStatus.Connected -> MekambColors.Success to "Connected" + (uiState.connectionLatencyMs?.let { " · $it ms" } ?: "")
                        ConnectionStatus.Failed -> MekambColors.Danger to "Connection failed"
                        ConnectionStatus.Checking -> MekambColors.TextMuted to "Checking…"
                        ConnectionStatus.Unknown -> MekambColors.TextMuted to "Not tested"
                    }
                    Box(Modifier.size(8.dp).background(dot, CircleShape))
                    Text(label, color = dot, fontSize = 12.sp, modifier = Modifier.padding(start = 8.dp).weight(1f))
                    TextButton(onClick = { showServer = !showServer }) {
                        Text(if (showServer) "Hide" else "Server", color = MekambColors.Link, fontSize = 12.sp)
                    }
                }
                if (showServer) {
                    OutlinedTextField(
                        endpoint,
                        onValueChange = { endpoint = it },
                        label = { Text("Server URL (e.g. 192.168.1.50:8000)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    )
                    TextButton(onClick = {
                        viewModel.setApiEndpoint(endpoint)
                        viewModel.testConnection()
                    }) { Text(if (uiState.connectionStatus == ConnectionStatus.Checking) "Testing…" else "Test connection", color = MekambColors.Accent) }
                }
            }
            Spacer(Modifier.height(18.dp))

            // ── Mode switch ──
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                listOf("login" to "Log in", "register" to "Sign up").forEach { (value, label) ->
                    TextButton(onClick = { mode = value }) {
                        Text(label, color = if (mode == value) MekambColors.Accent else MekambColors.TextMuted, fontWeight = FontWeight.Bold)
                    }
                }
            }
            Spacer(Modifier.height(6.dp))

            // ── Fields ──
            if (mode == "login") {
                OutlinedTextField(identifier, { identifier = it }, label = { Text("Email or username") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            } else {
                OutlinedTextField(email, { email = it }, label = { Text("Email") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(username, { username = it }, label = { Text("Username") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            }
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                password,
                { password = it },
                label = { Text("Password") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(16.dp))

            Button(
                onClick = {
                    // Persist any edited endpoint before authenticating.
                    if (endpoint.trim() != uiState.apiEndpoint) viewModel.setApiEndpoint(endpoint)
                    if (mode == "login") viewModel.login(identifier, password) else viewModel.register(email, username, password)
                    password = ""
                },
                enabled = !uiState.isLoading,
                colors = ButtonDefaults.buttonColors(containerColor = MekambColors.Accent, contentColor = MekambColors.BackgroundAlt),
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) {
                Text(if (mode == "login") "Log In" else "Create Account", fontSize = 16.sp, fontWeight = FontWeight.Bold)
            }

            uiState.statusMessage?.let { message ->
                Spacer(Modifier.height(14.dp))
                Text(
                    message,
                    color = if (uiState.isError) MekambColors.Danger else MekambColors.Success,
                    fontSize = 13.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            if (mode == "register") {
                Spacer(Modifier.height(10.dp))
                Text(
                    "New accounts must be approved by an admin before you can log in.",
                    color = MekambColors.TextFaint,
                    fontSize = 12.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

private val Color0E1420 = Color(0xFF0E1420)
