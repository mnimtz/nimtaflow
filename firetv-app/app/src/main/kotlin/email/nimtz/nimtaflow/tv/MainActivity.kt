package email.nimtz.nimtaflow.tv

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.lifecycle.lifecycleScope
import email.nimtz.nimtaflow.tv.ui.AppNavGraph
import email.nimtz.nimtaflow.tv.ui.theme.NimtaFlowTheme
import email.nimtz.nimtaflow.tv.util.Prefs
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val app = application as NimtaFlowApp
        val api  = app.api
        val prefs = app.prefs

        // Read persisted values synchronously so we can set the initial screen correctly
        val initialUrl   = runBlocking { prefs.serverUrl.first() }
        val initialToken = runBlocking { prefs.token.first() }

        // Apply stored URL/token to the API client
        if (initialUrl.isNotEmpty()) api.setBaseUrl(initialUrl)
        if (initialToken.isNotEmpty()) api.setToken(initialToken)

        setContent {
            NimtaFlowTheme {
                AppNavGraph(
                    api          = api,
                    initialUrl   = initialUrl,
                    initialToken = initialToken,
                    onServerSaved  = { url -> prefs.saveServerUrl(url) },
                    onTokensSaved  = { access, refresh -> prefs.saveTokens(access, refresh) },
                    onLogout       = { prefs.clearTokens() },
                )
            }
        }
    }
}
