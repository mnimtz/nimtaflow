package email.nimtz.nimtaflow.tv

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import email.nimtz.nimtaflow.tv.ui.AppNavGraph
import email.nimtz.nimtaflow.tv.ui.theme.Accent
import email.nimtz.nimtaflow.tv.ui.theme.BgDark
import email.nimtz.nimtaflow.tv.ui.theme.Muted
import email.nimtz.nimtaflow.tv.ui.theme.NimtaFlowTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val app = application as NimtaFlowApp
        val api = app.api
        val prefs = app.prefs

        // setContent MUSS synchron in onCreate laufen, sonst zeigt Android nur
        // den schwarzen windowBackground und die App wirkt eingefroren.
        // Prefs-Laden (DataStore, Disk-IO) passiert erst NACHDEM Compose steht.
        setContent {
            NimtaFlowTheme {
                var initialUrl by remember { mutableStateOf<String?>(null) }
                var initialToken by remember { mutableStateOf<String?>(null) }
                var loadError by remember { mutableStateOf<String?>(null) }

                LaunchedEffect(Unit) {
                    try {
                        val url = withContext(Dispatchers.IO) { prefs.serverUrl.first() }
                        val token = withContext(Dispatchers.IO) { prefs.token.first() }
                        if (url.isNotEmpty()) api.baseUrl = url.trimEnd('/')
                        if (token.isNotEmpty()) api.setToken(token)
                        initialUrl = url
                        initialToken = token
                    } catch (e: Exception) {
                        loadError = e.message ?: "Fehler beim Laden"
                        initialUrl = ""
                        initialToken = ""
                    }
                }

                if (initialUrl == null || initialToken == null) {
                    SplashScreen(errorText = loadError)
                } else {
                    AppNavGraph(
                        api = api,
                        initialUrl = initialUrl!!,
                        initialToken = initialToken!!,
                        onServerSaved = { url -> prefs.saveServerUrl(url) },
                        onTokensSaved = { access, refresh -> prefs.saveTokens(access, refresh) },
                        onLogout = { prefs.clearTokens() },
                    )
                }
            }
        }
    }
}

@Composable
private fun SplashScreen(errorText: String? = null) {
    Box(
        Modifier.fillMaxSize().background(BgDark),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            Text(
                "✦",
                color = Accent,
                fontSize = 72.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                "NimtaFlow",
                color = Accent,
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
            )
            if (errorText != null) {
                Text(
                    errorText,
                    color = Color(0xFFF87171),
                    fontSize = 13.sp,
                )
            } else {
                CircularProgressIndicator(
                    color = Muted,
                    strokeWidth = 2.dp,
                    modifier = Modifier.size(24.dp),
                )
            }
        }
    }
}
