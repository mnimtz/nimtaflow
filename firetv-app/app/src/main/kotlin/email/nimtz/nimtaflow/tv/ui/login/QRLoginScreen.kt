package email.nimtz.nimtaflow.tv.ui.login

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.ui.theme.*
import email.nimtz.nimtaflow.tv.util.generateQRBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

/**
 * Full-screen QR login for FireTV / tvOS.
 * 1. Requests a device code from the backend
 * 2. Renders it as a QR code + short code text
 * 3. Polls /api/device/token every 3 s until approved
 * 4. Calls onApproved(accessToken, refreshToken) when done
 */
@Composable
fun QRLoginScreen(
    api: APIClient,
    onApproved: (accessToken: String, refreshToken: String) -> Unit,
) {
    var userCode  by remember { mutableStateOf("") }
    var qrUrl     by remember { mutableStateOf("") }
    var deviceCode by remember { mutableStateOf("") }
    var error     by remember { mutableStateOf("") }
    var loading   by remember { mutableStateOf(true) }

    // Fetch device code once
    LaunchedEffect(Unit) {
        try {
            val resp = withContext(Dispatchers.IO) { api.requestDeviceCode() }
            userCode   = resp.userCode
            qrUrl      = resp.qrUrl
            deviceCode = resp.deviceCode
            loading    = false
        } catch (e: Exception) {
            error = "Verbindungsfehler: ${e.message}"
            loading = false
        }
    }

    // Poll for approval
    LaunchedEffect(deviceCode) {
        if (deviceCode.isEmpty()) return@LaunchedEffect
        while (true) {
            delay(3_000)
            try {
                val resp = withContext(Dispatchers.IO) { api.pollDeviceToken(deviceCode) }
                when (resp.status) {
                    "approved" -> {
                        val accessToken = resp.accessToken ?: ""
                        val refreshToken = resp.refreshToken ?: ""
                        onApproved(accessToken, refreshToken)
                        return@LaunchedEffect
                    }
                    "expired"  -> { error = "Code abgelaufen. Bitte neu laden."; return@LaunchedEffect }
                }
            } catch (_: Exception) { /* network blip — retry */ }
        }
    }

    Box(
        Modifier.fillMaxSize().background(BgDark),
        contentAlignment = Alignment.Center,
    ) {
        Row(
            Modifier.fillMaxSize().padding(horizontal = 80.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(72.dp),
        ) {
            // Left: QR code
            Box(
                Modifier
                    .size(280.dp)
                    .background(Color.White, RoundedCornerShape(16.dp))
                    .padding(12.dp),
                contentAlignment = Alignment.Center,
            ) {
                if (loading) {
                    CircularProgressIndicator(color = AccentDim)
                } else if (qrUrl.isNotEmpty()) {
                    val bmp = remember(qrUrl) { generateQRBitmap(qrUrl, 512) }
                    Image(
                        bitmap = bmp.asImageBitmap(),
                        contentDescription = "QR Code",
                        modifier = Modifier.fillMaxSize(),
                    )
                }
            }

            // Right: instructions
            Column(
                Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                Text("✦ NimtaFlow", color = Accent, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Text(
                    "Anmelden mit dem Smartphone",
                    color = OnSurface, fontSize = 28.sp, fontWeight = FontWeight.Bold,
                )
                Text(
                    "1. Öffne die Kamera-App auf deinem Handy\n" +
                    "2. Scanne den QR-Code\n" +
                    "3. Melde dich im Browser an\n" +
                    "4. Der TV entsperrt sich automatisch",
                    color = Muted, fontSize = 16.sp, lineHeight = 26.sp,
                )

                if (userCode.isNotEmpty()) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Oder gib diesen Code manuell ein:", color = Muted, fontSize = 13.sp)
                        Box(
                            Modifier
                                .border(2.dp, SurfaceHi, RoundedCornerShape(10.dp))
                                .background(Surface, RoundedCornerShape(10.dp))
                                .padding(horizontal = 20.dp, vertical = 10.dp),
                        ) {
                            Text(
                                userCode,
                                color = Accent,
                                fontSize = 32.sp,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace,
                                letterSpacing = 4.sp,
                            )
                        }
                    }
                }

                if (error.isNotEmpty()) {
                    Text(error, color = Color(0xFFF87171), fontSize = 14.sp)
                }

                if (!loading && error.isEmpty()) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            strokeWidth = 2.dp,
                            color = Muted,
                        )
                        Text("Warte auf Bestätigung…", color = Muted, fontSize = 14.sp)
                    }
                }
            }
        }
    }
}
