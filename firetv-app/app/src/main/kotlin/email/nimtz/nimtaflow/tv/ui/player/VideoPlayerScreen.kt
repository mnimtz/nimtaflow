package email.nimtz.nimtaflow.tv.ui.player

import android.net.Uri
import android.view.KeyEvent
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
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import coil.request.ImageRequest
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.ui.theme.*
import email.nimtz.nimtaflow.tv.util.formatDate
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Full-screen photo/video viewer.
 *
 * Fotos:
 *  ◀ ▶  vorheriges / nächstes Foto
 *  OK   Info ein/aus
 *  ▲    Favorit toggeln
 *  BACK schließen
 *
 * Videos:
 *  OK        Play / Pause
 *  ◀ ▶      -10 s / +10 s Seek (nicht Foto-Wechsel!)
 *  ▲        Favorit toggeln
 *  ▼ / BACK schließen
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
    val favoriteMap = remember { mutableStateMapOf<Int, Boolean>().also { m -> photos.forEach { m[it.id] = it.isFavorite } } }
    val scope = rememberCoroutineScope()

    val photo = photos.getOrNull(currentIndex)
    val isVideo = photo?.isVideo == true

    val focusRequester = remember { FocusRequester() }
    LaunchedEffect(currentIndex) { focusRequester.requestFocus() }

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
                    Key.DirectionUp -> {
                        photo ?: return@onKeyEvent false
                        val newVal = !(favoriteMap[photo.id] ?: photo.isFavorite)
                        favoriteMap[photo.id] = newVal
                        scope.launch { api.toggleFavorite(photo.id, newVal) }
                        true
                    }
                    else -> {
                        if (isVideo) {
                            // Video-Modus — Foto-Blätter deaktiviert, damit Seek+Play einheitlich sind
                            false
                        } else {
                            when (e.key) {
                                Key.DirectionLeft -> {
                                    currentIndex = (currentIndex - 1 + photos.size) % photos.size
                                    showInfo = false; true
                                }
                                Key.DirectionRight -> {
                                    currentIndex = (currentIndex + 1) % photos.size
                                    showInfo = false; true
                                }
                                Key.DirectionCenter, Key.Enter -> { showInfo = !showInfo; true }
                                else -> false
                            }
                        }
                    }
                }
            }
    ) {
        // ── Media ─────────────────────────────────────────────────────────────
        if (photo != null) {
            if (photo.isVideo) {
                VideoItem(
                    streamUrl = api.videoStreamUrl(photo.id),
                    onNext = if (photos.size > 1) {
                        { currentIndex = (currentIndex + 1) % photos.size }
                    } else null,
                    onPrev = if (photos.size > 1) {
                        { currentIndex = (currentIndex - 1 + photos.size) % photos.size }
                    } else null,
                    onDismiss = onDismiss,
                )
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
                OverlayIconButton(Icons.Default.Close, "Schließen", onClick = onDismiss)

                if (photos.size > 1) {
                    Text(
                        "${currentIndex + 1} / ${photos.size}",
                        color = Color.White.copy(0.8f), fontSize = 14.sp,
                    )
                }

                val isFav = favoriteMap[photo?.id] ?: photo?.isFavorite ?: false
                OverlayIconButton(
                    if (isFav) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                    "Favorit",
                    tint = if (isFav) Color(0xFFFF6B9D) else Color.White,
                    onClick = {
                        photo ?: return@OverlayIconButton
                        val newVal = !isFav
                        favoriteMap[photo.id] = newVal
                        scope.launch { api.toggleFavorite(photo.id, newVal) }
                    },
                )
            }
        }

        // ── Info overlay (nur Fotos) ─────────────────────────────────────────
        AnimatedVisibility(
            visible = !isVideo && showInfo && photo != null,
            enter = slideInVertically(initialOffsetY = { it }),
            exit  = slideOutVertically(targetOffsetY = { it }),
            modifier = Modifier.align(Alignment.BottomCenter),
        ) {
            photo?.let { InfoPanel(it) }
        }

        // ── Hint bar unten ─────────────────────────────────────────────────
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
                    if (isVideo) {
                        HintText("OK  Play/Pause")
                        HintText("◀ ▶  ±10 s")
                        HintText("▲  Favorit")
                        HintText("Zurück  Schließen")
                    } else {
                        HintText("◀ ▶  Blättern")
                        HintText("OK  Info")
                        HintText("▲  Favorit")
                    }
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

/**
 * Video-Player mit ExoPlayer + eigener D-Pad-Behandlung.
 *
 * Die eingebettete PlayerView übernimmt Fokus, damit ihre internen Controls
 * (Play/Pause, Seek) auf D-Pad reagieren. Zusätzlich handeln wir per
 * setControllerDispatchAsRunnable UP zum verbergen, DOWN zum schließen, damit
 * die Fernbedienung sich vertraut anfühlt.
 */
@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
@Composable
private fun VideoItem(
    streamUrl: String,
    onNext: (() -> Unit)?,
    onPrev: (() -> Unit)?,
    onDismiss: () -> Unit,
) {
    val ctx = LocalContext.current
    var loading by remember(streamUrl) { mutableStateOf(true) }
    var errorText by remember(streamUrl) { mutableStateOf<String?>(null) }

    val player = remember(streamUrl) {
        ExoPlayer.Builder(ctx).build().also { p ->
            val item = MediaItem.Builder().setUri(Uri.parse(streamUrl)).build()
            p.setMediaItem(item)
            p.prepare()
            p.playWhenReady = true
            p.addListener(object : Player.Listener {
                override fun onPlaybackStateChanged(state: Int) {
                    if (state == Player.STATE_READY || state == Player.STATE_ENDED) loading = false
                    if (state == Player.STATE_BUFFERING) loading = true
                }
                override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
                    loading = false
                    errorText = "Wiedergabefehler: ${error.errorCodeName}"
                }
            })
        }
    }
    DisposableEffect(player) { onDispose { player.release() } }

    val focus = remember { FocusRequester() }
    LaunchedEffect(streamUrl) {
        try { focus.requestFocus() } catch (_: Exception) {}
    }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(
            factory = { c ->
                PlayerView(c).also { pv ->
                    pv.player = player
                    pv.useController = true
                    pv.setShowNextButton(false)
                    pv.setShowPreviousButton(false)
                    pv.controllerAutoShow = true
                    pv.controllerShowTimeoutMs = 3000
                    pv.setShowFastForwardButton(true)
                    pv.setShowRewindButton(true)
                    pv.isFocusable = true
                    pv.isFocusableInTouchMode = true
                    pv.requestFocus()
                    // Custom Key-Handler: LEFT/RIGHT = ±10 s, UP=Foto-vor, DOWN=zurück
                    pv.setOnKeyListener { _, keyCode, event ->
                        if (event.action != KeyEvent.ACTION_DOWN) return@setOnKeyListener false
                        when (keyCode) {
                            KeyEvent.KEYCODE_DPAD_LEFT -> {
                                player.seekTo((player.currentPosition - 10_000L).coerceAtLeast(0))
                                pv.showController()
                                true
                            }
                            KeyEvent.KEYCODE_DPAD_RIGHT -> {
                                val dur = player.duration
                                val target = (player.currentPosition + 10_000L).coerceAtMost(if (dur > 0) dur else Long.MAX_VALUE)
                                player.seekTo(target)
                                pv.showController()
                                true
                            }
                            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER,
                            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> {
                                if (player.isPlaying) player.pause() else player.play()
                                pv.showController()
                                true
                            }
                            KeyEvent.KEYCODE_DPAD_UP -> { onNext?.invoke(); onNext != null }
                            KeyEvent.KEYCODE_DPAD_DOWN -> { onPrev?.invoke(); onPrev != null }
                            KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_ESCAPE -> {
                                onDismiss(); true
                            }
                            else -> false
                        }
                    }
                }
            },
            modifier = Modifier.fillMaxSize().focusRequester(focus),
        )
        if (loading && errorText == null) {
            CircularProgressIndicator(
                color = Accent,
                modifier = Modifier.align(Alignment.Center),
            )
        }
        errorText?.let { msg ->
            Column(
                Modifier.align(Alignment.Center).padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Icon(Icons.Default.ErrorOutline, null, tint = Color(0xFFF87171), modifier = Modifier.size(40.dp))
                Text(msg, color = Color.White, fontSize = 15.sp)
                Text("Zurück zum Schließen", color = Muted, fontSize = 13.sp)
            }
        }
    }
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
    Text(text, color = Color.White.copy(alpha = 0.6f), fontSize = 12.sp)
}
