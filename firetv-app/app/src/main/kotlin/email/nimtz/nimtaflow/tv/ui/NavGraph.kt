package email.nimtz.nimtaflow.tv.ui

import androidx.compose.runtime.*
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.ui.albums.AlbumsScreen
import email.nimtz.nimtaflow.tv.ui.gallery.GalleryScreen
import email.nimtz.nimtaflow.tv.ui.home.HomeScreen
import email.nimtz.nimtaflow.tv.ui.home.HomeTab
import email.nimtz.nimtaflow.tv.ui.login.QRLoginScreen
import email.nimtz.nimtaflow.tv.ui.memories.MemoriesScreen
import email.nimtz.nimtaflow.tv.ui.player.MediaViewerScreen
import email.nimtz.nimtaflow.tv.ui.setup.ServerSetupScreen
import kotlinx.coroutines.launch

enum class Screen { ServerSetup, Login, Home }

@Composable
fun AppNavGraph(
    api: APIClient,
    initialUrl: String,
    initialToken: String,
    onServerSaved: suspend (String) -> Unit,
    onTokensSaved: suspend (String, String) -> Unit,
    onLogout: suspend () -> Unit,
) {
    val scope = rememberCoroutineScope()

    var screen by remember {
        mutableStateOf(
            when {
                initialUrl.isEmpty() -> Screen.ServerSetup
                initialToken.isEmpty() -> Screen.Login
                else -> Screen.Home
            }
        )
    }
    var token by remember { mutableStateOf(initialToken) }
    var tab by remember { mutableStateOf(HomeTab.Gallery) }

    // Viewer overlay state
    var viewerPhotos by remember { mutableStateOf<List<Photo>?>(null) }
    var viewerIndex  by remember { mutableIntStateOf(0) }

    when (screen) {
        Screen.ServerSetup -> ServerSetupScreen { url ->
            api.setBaseUrl(url)
            scope.launch { onServerSaved(url) }
            screen = Screen.Login
        }

        Screen.Login -> QRLoginScreen(api) { access, refresh ->
            token = access
            api.setToken(access)
            scope.launch { onTokensSaved(access, refresh) }
            screen = Screen.Home
        }

        Screen.Home -> {
            HomeScreen(
                selectedTab = tab,
                onTabSelect = { tab = it },
                onLogout = {
                    scope.launch {
                        onLogout()
                        token = ""
                        api.setToken("")
                        screen = Screen.Login
                    }
                },
            ) {
                when (tab) {
                    HomeTab.Gallery   -> GalleryScreen(api, token)  { p, i -> viewerPhotos = p; viewerIndex = i }
                    HomeTab.Favorites -> GalleryScreen(api, token)  { p, i -> viewerPhotos = p; viewerIndex = i }
                    HomeTab.Albums    -> AlbumsScreen(api, token)   { p, i -> viewerPhotos = p; viewerIndex = i }
                    HomeTab.Memories  -> MemoriesScreen(api, token) { p, i -> viewerPhotos = p; viewerIndex = i }
                }
            }

            viewerPhotos?.let { photos ->
                MediaViewerScreen(
                    photos = photos,
                    startIndex = viewerIndex,
                    api = api,
                    token = token,
                    onDismiss = { viewerPhotos = null },
                )
            }
        }
    }
}
