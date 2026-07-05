package email.nimtz.nimtaflow.tv.screensaver

import android.content.Context
import android.service.dreams.DreamService
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner
import androidx.savedstate.SavedStateRegistry
import androidx.savedstate.SavedStateRegistryController
import androidx.savedstate.SavedStateRegistryOwner
import coil.compose.AsyncImage
import coil.request.ImageRequest
import email.nimtz.nimtaflow.tv.NimtaFlowApp
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Photo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

class NimtaFlowDreamService : DreamService() {

    private val composeLifecycleOwner = ComposeLifecycleOwner()

    override fun onCreate() {
        super.onCreate()
        composeLifecycleOwner.onCreate()
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        isFullscreen = true
        isInteractive = false
        composeLifecycleOwner.onStart()

        val view = ComposeView(this)
        view.setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnDetachedFromWindow)
        setViewTreeOwners(view, composeLifecycleOwner)
        view.setContent {
            CompositionLocalProvider(LocalViewModelStoreOwner provides composeLifecycleOwner) {
                ScreensaverSlideshow(applicationContext)
            }
        }
        setContentView(view)
    }

    override fun onDreamingStarted() {
        super.onDreamingStarted()
        composeLifecycleOwner.onResume()
    }

    override fun onDreamingStopped() {
        composeLifecycleOwner.onPause()
        super.onDreamingStopped()
    }

    override fun onDetachedFromWindow() {
        composeLifecycleOwner.onStop()
        super.onDetachedFromWindow()
    }

    override fun onDestroy() {
        composeLifecycleOwner.onDestroy()
        super.onDestroy()
    }
}

/**
 * Sets ViewTree lifecycle + saved-state owners via reflection.
 * Direct imports of ViewTreeLifecycleOwner / ViewTreeSavedStateRegistryOwner fail under
 * Kotlin K2 + Lifecycle 2.8.x KMP artifacts, so we reach them reflectively at runtime.
 */
private fun setViewTreeOwners(view: android.view.View, owner: ComposeLifecycleOwner) {
    runCatching {
        Class.forName("androidx.lifecycle.ViewTreeLifecycleOwner")
            .getMethod("set", android.view.View::class.java, androidx.lifecycle.LifecycleOwner::class.java)
            .invoke(null, view, owner)
    }
    runCatching {
        Class.forName("androidx.savedstate.ViewTreeSavedStateRegistryOwner")
            .getMethod("set", android.view.View::class.java, androidx.savedstate.SavedStateRegistryOwner::class.java)
            .invoke(null, view, owner)
    }
}

/** Minimal LifecycleOwner + SavedStateRegistryOwner + ViewModelStoreOwner for use in Services. */
private class ComposeLifecycleOwner :
    LifecycleOwner, SavedStateRegistryOwner, ViewModelStoreOwner {

    private val registry    = LifecycleRegistry(this)
    private val ssrCtrl     = SavedStateRegistryController.create(this)
    private val vmStore     = ViewModelStore()

    override val lifecycle: Lifecycle             get() = registry
    override val savedStateRegistry: SavedStateRegistry get() = ssrCtrl.savedStateRegistry
    override val viewModelStore: ViewModelStore   get() = vmStore

    fun onCreate()  { ssrCtrl.performAttach(); ssrCtrl.performRestore(null); registry.handleLifecycleEvent(Lifecycle.Event.ON_CREATE) }
    fun onStart()   { registry.handleLifecycleEvent(Lifecycle.Event.ON_START) }
    fun onResume()  { registry.handleLifecycleEvent(Lifecycle.Event.ON_RESUME) }
    fun onPause()   { registry.handleLifecycleEvent(Lifecycle.Event.ON_PAUSE) }
    fun onStop()    { registry.handleLifecycleEvent(Lifecycle.Event.ON_STOP) }
    fun onDestroy() { registry.handleLifecycleEvent(Lifecycle.Event.ON_DESTROY); vmStore.clear() }
}

// ── Composable Slideshow ──────────────────────────────────────────────────────

@Composable
private fun ScreensaverSlideshow(context: Context) {
    val app     = context.applicationContext as NimtaFlowApp
    val prefs   = app.prefs
    val ssPrefs = remember { ScreensaverPrefs(context) }

    val token       by prefs.token.collectAsState(initial = "")
    val serverUrl   by prefs.serverUrl.collectAsState(initial = "")
    val mode        by ssPrefs.mode.collectAsState(initial = "all")
    val personRaw   by ssPrefs.personIds.collectAsState(initial = "")
    val albumRaw    by ssPrefs.albumIds.collectAsState(initial = "")
    val intervalSec by ssPrefs.intervalSec.collectAsState(initial = 10)
    val showInfo    by ssPrefs.showInfo.collectAsState(initial = false)

    var photos  by remember { mutableStateOf<List<Photo>>(emptyList()) }
    var idx     by remember { mutableIntStateOf(0) }
    var loading by remember { mutableStateOf(true) }

    // Fetch photos whenever auth or mode changes
    LaunchedEffect(token, serverUrl, mode, personRaw, albumRaw) {
        if (token.isBlank() || serverUrl.isBlank()) { loading = false; return@LaunchedEffect }
        loading = true
        val api = APIClient(serverUrl, token)
        photos = withContext(Dispatchers.IO) {
            runCatching {
                val allPhotos by lazy { api.photos(limit = 200).items.filter { !it.isVideo }.shuffled() }
                when (mode) {
                    "persons" -> {
                        val ids = ssPrefs.personIdSet(personRaw)
                        if (ids.isEmpty()) allPhotos
                        else ids.flatMap { id -> api.photos(limit = 100, personId = id).items }
                            .filter { !it.isVideo }.shuffled()
                    }
                    "albums" -> {
                        val ids = ssPrefs.albumIdSet(albumRaw)
                        if (ids.isEmpty()) allPhotos
                        else ids.flatMap { id -> api.albumPhotos(id, limit = 200).items }
                            .filter { !it.isVideo }.shuffled()
                    }
                    "highlights" -> api.photos(limit = 100, view = "favorites").items
                        .filter { !it.isVideo }.shuffled()
                    else -> allPhotos
                }
            }.getOrDefault(emptyList())
        }
        idx = 0
        loading = false
    }

    // Auto-advance
    LaunchedEffect(photos.size, intervalSec) {
        if (photos.isEmpty()) return@LaunchedEffect
        while (true) {
            delay(intervalSec * 1000L)
            idx = (idx + 1) % photos.size
        }
    }

    Box(Modifier.fillMaxSize().background(Color.Black), contentAlignment = Alignment.Center) {
        when {
            loading -> CircularProgressIndicator(color = Color.White.copy(alpha = 0.3f))
            photos.isEmpty() -> { /* no content — black screen */ }
            else -> {
                AnimatedContent(
                    targetState = idx,
                    transitionSpec = {
                        fadeIn(tween(2000)) togetherWith fadeOut(tween(2000))
                    },
                    label = "screensaver",
                ) { i ->
                    val photo = photos.getOrNull(i) ?: return@AnimatedContent
                    AsyncImage(
                        model = ImageRequest.Builder(context)
                            .data("$serverUrl/api/photos/${photo.id}/thumbnail?size=large")
                            .addHeader("Authorization", "Bearer $token")
                            .crossfade(false)
                            .build(),
                        contentDescription = null,
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Fit,
                    )
                }

                // Info-Overlay
                if (showInfo) {
                    photos.getOrNull(idx)?.let { p ->
                        Column(
                            Modifier
                                .align(Alignment.BottomStart)
                                .background(Color.Black.copy(alpha = 0.45f))
                                .fillMaxWidth()
                                .padding(horizontal = 40.dp, vertical = 20.dp),
                        ) {
                            p.locationName?.let {
                                Text(it, color = Color.White, fontSize = 18.sp)
                            }
                            p.takenAt?.let { ts ->
                                Text(
                                    formatDate(ts),
                                    color = Color.White.copy(alpha = 0.7f),
                                    fontSize = 14.sp,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun formatDate(ts: String): String = try {
    val instant = java.time.Instant.parse(ts)
    val zdt     = instant.atZone(java.time.ZoneId.systemDefault())
    val month   = zdt.month.getDisplayName(java.time.format.TextStyle.FULL, java.util.Locale.GERMAN)
    "${zdt.dayOfMonth}. $month ${zdt.year}"
} catch (_: Exception) { ts.take(10) }
