package email.nimtz.nimtaflow.tv.ui.player

import android.net.Uri
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
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import coil.request.ImageRequest
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.ui.theme.*
import email.nimtz.nimtaflow.tv.util.formatDate
import kotlinx.coroutines.delay

/**
 * Full-screen photo/video viewer.
 * D-pad LEFT/RIGHT → previous/next item
 * D-pad CENTER/OK  → play/pause (video) / show info (photo)
 * D-pad UP         → toggle favorite
 * D-pad BACK       → dismiss
 */
@Composable
fun MediaViewerScreen(
    photos: List<Photo>,
    startIndex: Int,
    api: APIClient,
    token: String,
    onDismiss: () -> Unit,
) {
    var currentIndex by remember { mutableIntStateOf(startIndex.coerceIn(0, photos.lastIndex)) }
    var showInfo by remember { mutableStateOf(false) }
    // Local copy of isFavorite so we can toggle optimistically without reloading the list
    val favoriteMap = remember { mutableStateMapOf<Int, Boolean>().also { m -> photos.forEach { m[it.id] = it.isFavorite } } }

    val focusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) { focusRequester.requestFocus() }

    // Auto-hide info after 5s
    LaunchedEffect(showInfo) {
        if (showInfo) { delay(5000); showInfo = false }
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
            .focusRequester(focusRequester)
            .focusable()
            .onKeyEvent { e ->
                if (e.type != KeyEventType.KeyDown) return@onKeyEvent false
                when (e.key) {
                    Key.Back, Key.Escape -> { onDismiss(); true }
                    Key.DirectionLeft  -> {
                        currentIndex = (currentIndex - 1 + photos.size) % photos.size
                        showInfo = false; true
                    }
                    Key.DirectionRight -> {
                        currentIndex = (currentIndex + 1) % photos.size
                        showInfo = false; true
                    }
                    Key.DirectionCenter, Key.Enter -> { showInfo = !showInfo; true }
                    Key.DirectionUp -> {
                        val photo = photos.getOrNull(currentIndex) ?: return@onKeyEvent false
                        val newVal = !(favoriteMap[photo.id] ?: photo.isFavorite)
                        favoriteMap[photo.id] = newVal
                        // Fire-and-forget
                        kotlinx.coroutines.MainScope().launch { api.toggleFavorite(photo.id, newVal) }
                        true
                    }
                    else -> false
                }
            }
    ) {
        val photo = photos.getOrNull(currentIndex)

        // ── Media ─────────────────────────────────────────────────────────────
        if (photo != null) {
            if (photo.isVideo) {
                VideoItem(api.streamUrl(photo.id), token)
            } else {
                PhotoItem(photo.id, api, token)
            }
        }

        // ── Top bar (always visible) ──────────────────────────────────────────
        Box(
            Modifier
                .fillMaxWidth()
                .height(80.dp)
                .align(Alignment.TopCenter)
                .background(
                    Brush.verticalGradient(listOf(Color.Black.copy(0.7f), Color.Transparent))
                )
        ) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // Close button
                OverlayIconButton(Icons.Default.Close, "Schließen", onClick = onDismiss)

                // Photo counter
                if (photos.size > 1) {
                    Text(
                        "${currentIndex + 1} / ${photos.size}",
                        color = Color.White.copy(0.8f), fontSize = 14.sp,
                    )
                }

                // Favorite button
                val isFav = favoriteMap[photo?.id] ?: photo?.isFavorite ?: false
                OverlayIconButton(
                    if (isFav) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                    "Favorit",
                    tint = if (isFav) Color(0xFFFF6B9D) else Color.White,
                    onClick = {
                        photo ?: return@OverlayIconButton
                        val newVal = !isFav
                        favoriteMap[photo.id] = newVal
                        kotlinx.coroutines.MainScope().launch { api.toggleFavorite(photo.id, newVal) }
                    },
                )
            }
        }

        // ── Info overlay (toggleable) ─────────────────────────────────────────
        AnimatedVisibility(
            visible = showInfo && photo != null,
            enter = slideInVertically(initialOffsetY = { it }),
            exit  = slideOutVertically(targetOffsetY = { it }),
            modifier = Modifier.align(Alignment.BottomCenter),
        ) {
            photo?.let { InfoPanel(it) }
        }

        // ── Hint bar at bottom (if no info) ───────────────────────────────────
        AnimatedVisibility(
            visible = !showInfo,
            enter = fadeIn(tween(300)),
            exit  = fadeOut(tween(300)),
            modifier = Modifier.align(Alignment.BottomCenter),
        ) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(60.dp)
                    .background(Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(0.6f)))),
                contentAlignment = Alignment.Center,
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                    HintText("◀ ▶  Blättern")
                    HintText("OK  Info")
                    HintText("▲  Favorit")
                }
            }
        }
    }
}

// ── Sub-composables ────────────────────────────────────────────────────────────

@Composable
private fun PhotoItem(photoId: Int, api: APIClient, token: String) {
    val ctx = LocalContext.current
    AsyncImage(
        model = ImageRequest.Builder(ctx)
            .data(api.thumbUrl(photoId, "large"))
            .addHeader("Authorization", "Bearer $token")
            .crossfade(true)
            .build(),
        contentDescription = null,
        contentScale = ContentScale.Fit,
        modifier = Modifier.fillMaxSize().background(Color.Black),
    )
}

@Composable
private fun VideoItem(streamUrl: String, token: String) {
    val ctx = LocalContext.current
    val player = remember {
        ExoPlayer.Builder(ctx).build().also { p ->
            val item = MediaItem.Builder()
                .setUri(Uri.parse(streamUrl))
                .build()
            p.setMediaItem(item)
            p.prepare()
            p.playWhenReady = true
        }
    }
    DisposableEffect(Unit) { onDispose { player.release() } }

    AndroidView(
        factory = { c ->
            PlayerView(c).also { pv ->
                pv.player = player
                pv.useController = true
                pv.setShowNextButton(false)
                pv.setShowPreviousButton(false)
            }
        },
        modifier = Modifier.fillMaxSize(),
    )
}

@Composable
private fun InfoPanel(photo: Photo) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(
                Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(0.92f))),
            )
            .padding(horizontal = 32.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        // Date
        val date = formatDate(photo.takenAt)
        if (date.isNotEmpty()) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Default.CalendarToday, null, tint = Accent, modifier = Modifier.size(16.dp))
                Text(date, color = OnSurface, fontSize = 15.sp)
            }
        }

        // Location
        val loc = photo.locationName
        if (!loc.isNullOrBlank()) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Default.LocationOn, null, tint = Accent, modifier = Modifier.size(16.dp))
                Text(loc, color = OnSurface, fontSize = 15.sp)
            }
        } else if (photo.latitude != null && photo.longitude != null) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Default.LocationOn, null, tint = Muted, modifier = Modifier.size(16.dp))
                Text(
                    "%.4f, %.4f".format(photo.latitude, photo.longitude),
                    color = Muted, fontSize = 13.sp,
                )
            }
        }

        // Resolution
        if (photo.width != null && photo.height != null) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Default.AspectRatio, null, tint = Muted, modifier = Modifier.size(16.dp))
                Text("${photo.width} × ${photo.height}", color = Muted, fontSize = 13.sp)
            }
        }
    }
}

@Composable
private fun OverlayIconButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    desc: String,
    tint: Color = Color.White,
    onClick: () -> Unit,
) {
    IconButton(onClick = onClick) {
        Icon(icon, desc, tint = tint, modifier = Modifier.size(28.dp))
    }
}

@Composable
private fun HintText(text: String) {
    Text(text, color = Color.White.copy(alpha = 0.5f), fontSize = 12.sp)
}

// Minimal coroutine launcher from non-composable lambdas
private fun kotlinx.coroutines.CoroutineScope.launch(block: suspend () -> Unit) =
    kotlinx.coroutines.launch(block = block)
