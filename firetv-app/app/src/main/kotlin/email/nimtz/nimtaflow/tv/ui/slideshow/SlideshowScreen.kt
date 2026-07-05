package email.nimtz.nimtaflow.tv.ui.slideshow

import androidx.compose.animation.*
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.*
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.ui.theme.Accent
import email.nimtz.nimtaflow.tv.util.formatDate
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

private val SPEEDS = listOf(3, 5, 10, 20)   // seconds

@Composable
fun SlideshowScreen(
    api: APIClient,
    token: String,
    onDismiss: () -> Unit,
) {
    var photos by remember { mutableStateOf<List<Photo>>(emptyList()) }
    var currentIndex by remember { mutableIntStateOf(0) }
    var paused by remember { mutableStateOf(false) }
    var speedIndex by remember { mutableIntStateOf(1) }   // default 5s
    var showControls by remember { mutableStateOf(true) }

    val intervalMs = SPEEDS[speedIndex] * 1000L
    val focusRequester = remember { FocusRequester() }

    // Load photos (up to 400, photos only — no videos for slideshow)
    LaunchedEffect(Unit) {
        val loaded = mutableListOf<Photo>()
        var page = 1
        withContext(Dispatchers.IO) {
            while (loaded.size < 400) {
                val resp = api.photos(page = page, limit = 100)
                loaded += resp.items.filter { !it.isVideo }
                if (resp.items.size < 100) break
                page++
            }
        }
        photos = loaded.shuffled()   // random order for screensaver feel
    }

    // Auto-advance — photos.size in keys so the effect restarts when photos finish loading
    LaunchedEffect(currentIndex, paused, speedIndex, photos.size) {
        if (!paused && photos.isNotEmpty()) {
            delay(intervalMs)
            currentIndex = (currentIndex + 1) % photos.size
        }
    }

    // Auto-hide controls after 4s
    LaunchedEffect(showControls) {
        if (showControls) {
            delay(4000)
            showControls = false
        }
    }

    // Request focus so D-pad key events land here
    LaunchedEffect(Unit) { focusRequester.requestFocus() }

    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
            .focusRequester(focusRequester)
            .focusable()
            .onKeyEvent { e ->
                if (e.type != KeyEventType.KeyDown) return@onKeyEvent false
                showControls = true
                when (e.key) {
                    Key.Back, Key.Escape -> { onDismiss(); true }
                    Key.DirectionLeft  -> {
                        if (photos.isNotEmpty())
                            currentIndex = (currentIndex - 1 + photos.size) % photos.size
                        true
                    }
                    Key.DirectionRight -> {
                        if (photos.isNotEmpty())
                            currentIndex = (currentIndex + 1) % photos.size
                        true
                    }
                    Key.DirectionCenter, Key.Enter -> { paused = !paused; true }
                    Key.DirectionUp -> {
                        speedIndex = (speedIndex + 1) % SPEEDS.size; true
                    }
                    Key.DirectionDown -> {
                        speedIndex = (speedIndex - 1 + SPEEDS.size) % SPEEDS.size; true
                    }
                    else -> false
                }
            }
    ) {
        // ── Photo ────────────────────────────────────────────────────────────
        if (photos.isNotEmpty()) {
            Crossfade(
                targetState = currentIndex,
                animationSpec = tween(900),
                label = "slideshow_crossfade",
            ) { idx ->
                val photo = photos.getOrNull(idx) ?: return@Crossfade
                AsyncImage(
                    model = ImageRequest.Builder(LocalContext.current)
                        .data(api.thumbUrl(photo.id, "large"))
                        .addHeader("Authorization", "Bearer $token")
                        .crossfade(false)
                        .build(),
                    contentDescription = null,
                    contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxSize().background(Color.Black),
                )
            }
        } else {
            // Loading
            CircularProgressIndicator(
                color = Accent,
                modifier = Modifier.align(Alignment.Center),
            )
        }

        // ── Controls overlay (auto-hide) ──────────────────────────────────
        AnimatedVisibility(
            visible = showControls,
            enter = fadeIn(animationSpec = tween(300)),
            exit  = fadeOut(animationSpec = tween(600)),
            modifier = Modifier.fillMaxSize(),
        ) {
            Box(Modifier.fillMaxSize()) {
                // Bottom gradient
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(160.dp)
                        .align(Alignment.BottomCenter)
                        .background(
                            Brush.verticalGradient(
                                listOf(Color.Transparent, Color.Black.copy(alpha = 0.85f))
                            )
                        )
                )

                // Info bar
                Row(
                    Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .padding(horizontal = 32.dp, vertical = 24.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    // Photo count
                    if (photos.isNotEmpty()) {
                        Text(
                            "${currentIndex + 1} / ${photos.size}",
                            color = Color.White.copy(alpha = 0.8f), fontSize = 14.sp,
                        )
                    }

                    // Center: pause icon + speed
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(20.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            if (paused) Icons.Default.PlayArrow else Icons.Default.Pause,
                            contentDescription = null,
                            tint = Color.White,
                            modifier = Modifier.size(20.dp),
                        )
                        ControlHint("◀ ▶  Bild wechseln")
                        ControlHint("OK  Pause")
                        ControlHint("▲ ▼  Tempo: ${SPEEDS[speedIndex]}s")
                    }

                    // Date of current photo
                    Text(
                        formatDate(photos.getOrNull(currentIndex)?.takenAt),
                        color = Color.White.copy(alpha = 0.8f), fontSize = 14.sp,
                    )
                }
            }
        }

        // ── Pause indicator ──────────────────────────────────────────────
        if (paused) {
            Box(
                Modifier
                    .align(Alignment.Center)
                    .background(Color.Black.copy(alpha = 0.55f), RoundedCornerShape(50))
                    .padding(24.dp),
            ) {
                Icon(Icons.Default.Pause, null, tint = Color.White, modifier = Modifier.size(52.dp))
            }
        }
    }
}

@Composable
private fun ControlHint(text: String) {
    Text(
        text,
        color = Color.White.copy(alpha = 0.55f),
        fontSize = 12.sp,
        fontWeight = FontWeight.Normal,
    )
}
