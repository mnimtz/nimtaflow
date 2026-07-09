package email.nimtz.nimtaflow.tv.ui

import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.ui.albums.AlbumsScreen
import email.nimtz.nimtaflow.tv.ui.settings.FireTVSettingsScreen
import email.nimtz.nimtaflow.tv.ui.gallery.GalleryScreen
import email.nimtz.nimtaflow.tv.ui.home.DashboardScreen
import email.nimtz.nimtaflow.tv.ui.home.HomeScreen
import email.nimtz.nimtaflow.tv.ui.home.HomeTab
import email.nimtz.nimtaflow.tv.ui.login.QRLoginScreen
import email.nimtz.nimtaflow.tv.ui.memories.MemoriesScreen
import email.nimtz.nimtaflow.tv.ui.people.PeopleScreen
import email.nimtz.nimtaflow.tv.ui.player.MediaViewerScreen
import email.nimtz.nimtaflow.tv.ui.setup.ServerSetupScreen
import email.nimtz.nimtaflow.tv.ui.slideshow.SlideshowScreen
import email.nimtz.nimtaflow.tv.util.ReleaseInfo
import email.nimtz.nimtaflow.tv.util.UpdateChecker
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

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
    val context = LocalContext.current
    val prefs = (context.applicationContext as email.nimtz.nimtaflow.tv.NimtaFlowApp).prefs

    // Update-Check (10 s nach Start damit UI schon steht)
    var availableRelease by remember { mutableStateOf<ReleaseInfo?>(null) }
    var updateProgress   by remember { mutableStateOf(-1) }
    val lastInstalled    by prefs.lastInstalledRelease.collectAsState(initial = "")

    LaunchedEffect(Unit) {
        delay(10_000)
        val release = UpdateChecker.fetchLatestRelease() ?: return@LaunchedEffect
        if (UpdateChecker.isNewer(release.publishedAt, lastInstalled)) {
            availableRelease = release
        }
    }

    var screen by remember {
        mutableStateOf(
            when {
                initialUrl.isEmpty()   -> Screen.ServerSetup
                initialToken.isEmpty() -> Screen.Login
                else                   -> Screen.Home
            }
        )
    }
    var token by remember { mutableStateOf(initialToken) }
    val isAdmin by prefs.isAdmin.collectAsState(initial = false)
    var tab by remember { mutableStateOf(HomeTab.Home) }

    val onUnauthorized: () -> Unit = {
        scope.launch {
            onLogout()
            token = ""
            api.setToken("")
            screen = Screen.Login
        }
    }

    var viewerPhotos by remember { mutableStateOf<List<Photo>?>(null) }
    var viewerIndex  by remember { mutableIntStateOf(0) }
    var slideshowActive by remember { mutableStateOf(false) }

    when (screen) {
        Screen.ServerSetup -> ServerSetupScreen { url ->
            api.baseUrl = url.trimEnd('/')
            scope.launch { onServerSaved(url) }
            screen = Screen.Login
        }

        Screen.Login -> QRLoginScreen(api) { access, refresh ->
            token = access
            api.setToken(access)
            scope.launch {
                onTokensSaved(access, refresh)
                val me = withContext(Dispatchers.IO) { api.me() }
                prefs.saveIsAdmin(me?.role == "admin")
            }
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
                updateRelease = availableRelease,
                updateProgress = updateProgress,
                onInstallUpdate = {
                    availableRelease?.let { release ->
                        scope.launch {
                            updateProgress = 0
                            try {
                                UpdateChecker.downloadAndInstall(
                                    context = context,
                                    downloadUrl = release.downloadUrl,
                                    onProgress = { updateProgress = it },
                                )
                                prefs.saveLastInstalledRelease(release.publishedAt)
                            } catch (_: Exception) {
                            } finally {
                                updateProgress = -1
                                availableRelease = null
                            }
                        }
                    }
                },
            ) {
                when (tab) {
                    HomeTab.Home      -> DashboardScreen(
                        api = api,
                        token = token,
                        onOpenGallery = { tab = HomeTab.Gallery },
                        onOpenAlbums = { tab = HomeTab.Albums },
                        onOpenPeople = { tab = HomeTab.People },
                        onOpenMemories = { tab = HomeTab.Memories },
                        onOpenFavorites = { tab = HomeTab.Favorites },
                        onOpenSlideshow = { slideshowActive = true },
                        onPhotoSelected = { p, i -> viewerPhotos = p; viewerIndex = i },
                    )
                    HomeTab.Gallery   -> GalleryScreen(
                        api = api, token = token, view = "library",
                        onPhotoSelected = { p, i -> viewerPhotos = p; viewerIndex = i },
                        onStartSlideshow = { slideshowActive = true },
                    )
                    HomeTab.Favorites -> GalleryScreen(
                        api = api, token = token, view = "favorites",
                        onPhotoSelected = { p, i -> viewerPhotos = p; viewerIndex = i },
                    )
                    HomeTab.Albums    -> AlbumsScreen(api, token) { p, i -> viewerPhotos = p; viewerIndex = i }
                    HomeTab.People    -> PeopleScreen(api, token, isAdmin) { p, i -> viewerPhotos = p; viewerIndex = i }
                    HomeTab.Memories  -> MemoriesScreen(api, token) { p, i -> viewerPhotos = p; viewerIndex = i }
                    HomeTab.Settings  -> FireTVSettingsScreen(api)
                }
            }

            // Slideshow overlay (full-screen, above everything)
            if (slideshowActive) {
                SlideshowScreen(
                    api = api,
                    token = token,
                    onDismiss = { slideshowActive = false },
                )
            }

            // Media viewer overlay
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
