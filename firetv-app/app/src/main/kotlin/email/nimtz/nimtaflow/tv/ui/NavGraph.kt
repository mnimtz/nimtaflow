package email.nimtz.nimtaflow.tv.ui

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.api.UnauthorizedException
import email.nimtz.nimtaflow.tv.ui.albums.AlbumsScreen
import email.nimtz.nimtaflow.tv.ui.settings.FireTVSettingsScreen
import email.nimtz.nimtaflow.tv.ui.gallery.GalleryScreen
import email.nimtz.nimtaflow.tv.ui.home.HomeScreen
import email.nimtz.nimtaflow.tv.ui.home.HomeTab
import email.nimtz.nimtaflow.tv.ui.login.QRLoginScreen
import email.nimtz.nimtaflow.tv.ui.memories.MemoriesScreen
import email.nimtz.nimtaflow.tv.ui.people.PeopleScreen
import email.nimtz.nimtaflow.tv.ui.player.MediaViewerScreen
import email.nimtz.nimtaflow.tv.ui.setup.ServerSetupScreen
import email.nimtz.nimtaflow.tv.ui.slideshow.SlideshowScreen
import email.nimtz.nimtaflow.tv.ui.theme.Accent
import email.nimtz.nimtaflow.tv.util.ReleaseInfo
import email.nimtz.nimtaflow.tv.util.UpdateChecker
import kotlinx.coroutines.delay
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
    val context = LocalContext.current
    val prefs = (context.applicationContext as email.nimtz.nimtaflow.tv.NimtaFlowApp).prefs

    // Update-Check beim Start (einmalig, 10 s nach Launch damit UI schon steht)
    var availableRelease by remember { mutableStateOf<ReleaseInfo?>(null) }
    var updateProgress   by remember { mutableStateOf(-1) }   // -1 = idle, 0-100 = downloading
    val lastInstalled    by prefs.lastInstalledRelease.collectAsState(initial = "")

    LaunchedEffect(Unit) {
        delay(10_000)
        val release = UpdateChecker.fetchLatestRelease() ?: return@LaunchedEffect
        if (UpdateChecker.isNewer(release.publishedAt, lastInstalled)) {
            availableRelease = release
        }
    }

    // Globaler 401-Handler: bei abgelaufenem Token → sofort zurück zum Login
    val onUnauthorized: () -> Unit = {
        scope.launch {
            onLogout()
            token = ""
            api.setToken("")
            screen = Screen.Login
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
    var tab by remember { mutableStateOf(HomeTab.Gallery) }

    // Media viewer overlay
    var viewerPhotos by remember { mutableStateOf<List<Photo>?>(null) }
    var viewerIndex  by remember { mutableIntStateOf(0) }

    // Slideshow overlay
    var slideshowActive by remember { mutableStateOf(false) }

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

        Screen.Home -> Box(Modifier.fillMaxSize()) {
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
                    HomeTab.Gallery   -> GalleryScreen(
                        api = api, token = token, view = "library",
                        onPhotoSelected = { p, i -> viewerPhotos = p; viewerIndex = i },
                        onStartSlideshow = { slideshowActive = true },
                    )
                    HomeTab.Favorites -> GalleryScreen(
                        api = api, token = token, view = "favorites",
                        onPhotoSelected = { p, i -> viewerPhotos = p; viewerIndex = i },
                    )
                    HomeTab.Albums    -> AlbumsScreen(api, token)   { p, i -> viewerPhotos = p; viewerIndex = i }
                    HomeTab.People    -> PeopleScreen(api, token)   { p, i -> viewerPhotos = p; viewerIndex = i }
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

            // Update-Banner (oben rechts, erscheint wenn neue Version verfügbar)
            availableRelease?.let { release ->
                Box(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(24.dp),
                ) {
                    Card(
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = Color(0xCC1A1A2E)),
                        elevation = CardDefaults.cardElevation(8.dp),
                    ) {
                        Column(
                            modifier = Modifier.padding(20.dp).widthIn(max = 340.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                Icon(
                                    Icons.Filled.SystemUpdate,
                                    contentDescription = null,
                                    tint = Accent,
                                    modifier = Modifier.size(22.dp),
                                )
                                Text(
                                    text = "Update verfügbar",
                                    color = Color.White,
                                    fontSize = 16.sp,
                                )
                            }

                            Text(
                                text = release.releaseName,
                                color = Color(0xFFAAAAAA),
                                fontSize = 13.sp,
                            )

                            if (updateProgress in 0..100) {
                                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    LinearProgressIndicator(
                                        progress = { updateProgress / 100f },
                                        modifier = Modifier.fillMaxWidth(),
                                        color = Accent,
                                        trackColor = Color(0xFF333355),
                                    )
                                    Text(
                                        text = "Herunterladen… $updateProgress %",
                                        color = Color(0xFFAAAAAA),
                                        fontSize = 12.sp,
                                    )
                                }
                            } else {
                                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    TextButton(onClick = { availableRelease = null }) {
                                        Text("Später", color = Color(0xFF888888))
                                    }
                                    Button(
                                        onClick = {
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
                                                    // silent — user sees nothing happen, can retry
                                                } finally {
                                                    updateProgress = -1
                                                    availableRelease = null
                                                }
                                            }
                                        },
                                        colors = ButtonDefaults.buttonColors(containerColor = Accent),
                                    ) {
                                        Text("Jetzt installieren", color = Color.White)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
