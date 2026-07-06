package email.nimtz.nimtaflow.tv

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.lifecycle.lifecycleScope
import email.nimtz.nimtaflow.tv.ui.AppNavGraph
import email.nimtz.nimtaflow.tv.ui.theme.NimtaFlowTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val app = application as NimtaFlowApp
        val api  = app.api
        val prefs = app.prefs

        lifecycleScope.launch {
            val initialUrl   = withContext(Dispatchers.IO) { prefs.serverUrl.first() }
            val initialToken = withContext(Dispatchers.IO) { prefs.token.first() }

            if (initialUrl.isNotEmpty()) api.baseUrl = initialUrl.trimEnd('/')
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
}
