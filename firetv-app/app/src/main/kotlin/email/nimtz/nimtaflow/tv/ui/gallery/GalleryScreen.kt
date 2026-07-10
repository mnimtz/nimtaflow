package email.nimtz.nimtaflow.tv.ui.gallery

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
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
import email.nimtz.nimtaflow.tv.ui.theme.*
import email.nimtz.nimtaflow.tv.util.formatMonthYear
import email.nimtz.nimtaflow.tv.util.monthKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Pair of (photo, its global index in the flat `photos` list) */
private data class IndexedPhoto(val photo: Photo, val idx: Int)

@Composable
fun GalleryScreen(
    api: APIClient,
    token: String,
    view: String = "library",        // "library" | "favorites"
    onPhotoSelected: (List<Photo>, Int) -> Unit,
    onStartSlideshow: (() -> Unit)? = null,
) {
    var photos by remember { mutableStateOf<List<Photo>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var page by remember { mutableIntStateOf(1) }
    var hasMore by remember { mutableStateOf(true) }
    val gridState = rememberLazyGridState()

    suspend fun loadPage(p: Int) {
        try {
            val resp = withContext(Dispatchers.IO) { api.photos(page = p, limit = 60, view = view) }
            photos = if (p == 1) resp.items else photos + resp.items
            hasMore = resp.items.size >= resp.limit
        } catch (_: Exception) {
            hasMore = false
        } finally {
            loading = false
        }
    }

    LaunchedEffect(view) { page = 1; hasMore = true; loadPage(1) }

    // Infinite scroll trigger
    val lastVisible by remember {
        derivedStateOf { gridState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }
    }
    LaunchedEffect(lastVisible) {
        if (hasMore && !loading && lastVisible >= photos.size - 12) {
            loading = true; page++; loadPage(page)
        }
    }

    // Group photos by month for section headers.
    // WICHTIG: die flache Anzeige-Reihenfolge kann von der Server-Reihenfolge
    // abweichen (Server: newest first — aber wenn Import-Batches vermischt sind,
    // ist die Chronologie pro Monat nicht 1:1 in photos). Wir brauchen deshalb
    // eine `flatPhotos`-Liste die exakt der grouped-Reihenfolge folgt, damit der
    // MediaViewer beim Klick auf ein Foto das RICHTIGE öffnet.
    val grouped: List<Pair<String, List<IndexedPhoto>>> = remember(photos) {
        var idx = 0
        photos
            .groupBy { monthKey(it.takenAt) }
            .entries
            .sortedByDescending { it.key }
            .map { (key, group) ->
                val label = formatMonthYear(group.firstOrNull()?.takenAt)
                label to group.map { p -> IndexedPhoto(p, idx++) }
            }
    }
    val flatPhotos = remember(grouped) {
        grouped.flatMap { (_, ips) -> ips.map { it.photo } }
    }

    if (loading && photos.isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = Accent)
        }
        return
    }

    // Erste PhotoCard bekommt initialen Fokus, sobald Fotos geladen sind.
    val firstCardFocus = remember { FocusRequester() }
    LaunchedEffect(photos.isNotEmpty()) {
        if (photos.isNotEmpty()) {
            try { firstCardFocus.requestFocus() } catch (_: Exception) {}
        }
    }

    LazyVerticalGrid(
        columns = GridCells.Adaptive(minSize = 220.dp),
        state = gridState,
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.fillMaxSize(),
    ) {
        // ── Diashow button (first row) ─────────────────────────────────────
        if (onStartSlideshow != null) {
            item(span = { GridItemSpan(maxLineSpan) }) {
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 12.dp),
                    horizontalArrangement = Arrangement.End,
                ) {
                    SlideshowButton(onClick = onStartSlideshow)
                }
            }
        }

        // ── Grouped sections ───────────────────────────────────────────────
        grouped.forEach { (monthLabel, indexedPhotos) ->
            // Month header
            item(span = { GridItemSpan(maxLineSpan) }) {
                Text(
                    monthLabel,
                    color = OnSurface,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(top = 16.dp, bottom = 4.dp),
                )
            }

            // Photos in this month — nutzt flatPhotos (grouped-Reihenfolge)
            // damit der Index zur richtigen Liste passt.
            items(indexedPhotos, key = { it.photo.id }) { (photo, globalIdx) ->
                PhotoCard(
                    photo, api, token,
                    onClick = { onPhotoSelected(flatPhotos, globalIdx) },
                    modifier = if (globalIdx == 0) Modifier.focusRequester(firstCardFocus) else Modifier,
                )
            }
        }

        // Loading more indicator
        if (loading && photos.isNotEmpty()) {
            item(span = { GridItemSpan(maxLineSpan) }) {
                Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Accent, modifier = Modifier.size(24.dp))
                }
            }
        }
    }
}

@Composable
private fun SlideshowButton(onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(8.dp))
            .border(1.dp, if (focused) Accent else Accent.copy(alpha = 0.4f), RoundedCornerShape(8.dp))
            .background(if (focused) AccentDim.copy(alpha = 0.3f) else Color.Transparent)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)) { onClick(); true } else false
            }
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Default.PlayCircle, null, tint = Accent, modifier = Modifier.size(20.dp))
        Text("Diashow starten", color = Accent, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

// ── PhotoCard (shared across screens) ─────────────────────────────────────────

@Composable
fun PhotoCard(
    photo: Photo,
    api: APIClient,
    token: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var focused by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    val scale by androidx.compose.animation.core.animateFloatAsState(
        targetValue = if (focused) 1.06f else 1f,
        animationSpec = androidx.compose.animation.core.tween(180),
        label = "photoCardScale",
    )

    Box(
        modifier = modifier
            .aspectRatio(1f)
            .graphicsLayer {
                scaleX = scale
                scaleY = scale
            }
            .clip(RoundedCornerShape(12.dp))
            .border(
                width = if (focused) 3.dp else 0.dp,
                color = if (focused) Accent else Color.Transparent,
                shape = RoundedCornerShape(12.dp),
            )
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)) {
                    onClick(); true
                } else false
            }
    ) {
        AsyncImage(
            model = ImageRequest.Builder(ctx)
                .data(api.thumbUrl(photo.id, "medium"))
                .addHeader("Authorization", "Bearer $token")
                .crossfade(true)
                .build(),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxSize().background(SurfaceHi),
        )
        if (photo.isVideo) {
            Box(
                Modifier
                    .align(Alignment.Center)
                    .background(Color.Black.copy(alpha = 0.55f), RoundedCornerShape(50))
                    .padding(10.dp),
            ) {
                Icon(Icons.Default.PlayArrow, null, tint = Color.White, modifier = Modifier.size(28.dp))
            }
        }
    }
}
