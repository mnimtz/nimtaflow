package email.nimtz.nimtaflow.tv.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
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
import email.nimtz.nimtaflow.tv.api.Album
import email.nimtz.nimtaflow.tv.api.MemoryGroup
import email.nimtz.nimtaflow.tv.api.Person
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.ui.GridDensity
import email.nimtz.nimtaflow.tv.ui.LocalGridDensity
import email.nimtz.nimtaflow.tv.ui.LocalPeopleSort
import email.nimtz.nimtaflow.tv.ui.PeopleSort
import email.nimtz.nimtaflow.tv.ui.theme.*
import email.nimtz.nimtaflow.tv.util.formatDate
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Home / Startseite — Netflix-Style Content-Rails.
 *
 *  ┌───────────────────────────────────────────┐
 *  │              HERO (Hintergrundfoto)        │
 *  │  Titel-Overlay + Aktions-Hint              │
 *  └───────────────────────────────────────────┘
 *  ▸ Zuletzt hinzugefügt   [Rail]
 *  ▸ Erinnerungen          [Rail]
 *  ▸ Personen              [Rail]
 *  ▸ Alben                 [Rail]
 */
@Composable
fun DashboardScreen(
    api: APIClient,
    token: String,
    onOpenGallery: () -> Unit,
    onOpenAlbums: () -> Unit,
    onOpenPeople: () -> Unit,
    onOpenMemories: () -> Unit,
    onOpenFavorites: () -> Unit,
    onOpenSlideshow: () -> Unit,
    onPhotoSelected: (List<Photo>, Int) -> Unit,
) {
    var recent by remember { mutableStateOf<List<Photo>>(emptyList()) }
    var memories by remember { mutableStateOf<List<MemoryGroup>>(emptyList()) }
    var people by remember { mutableStateOf<List<Person>>(emptyList()) }
    var albums by remember { mutableStateOf<List<Album>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }

    val sort = LocalPeopleSort.current
    LaunchedEffect(sort) {
        withContext(Dispatchers.IO) {
            runCatching { recent = api.photos(limit = 20).items }
            runCatching { memories = api.memories() }
            runCatching {
                val all = api.persons().filter { it.name.isNotBlank() }
                people = when (sort) {
                    PeopleSort.ByPhotoCount -> all.sortedByDescending { it.photoCount }.take(20)
                    PeopleSort.ByName       -> all.sortedBy { it.name.lowercase() }.take(20)
                }
            }
            runCatching { albums = api.albums().take(20) }
        }
        loading = false
    }

    if (loading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = Accent)
        }
        return
    }

    val heroPhoto = memories.firstOrNull()?.items?.firstOrNull() ?: recent.firstOrNull()
    val heroTitle = memories.firstOrNull()?.let {
        if (it.yearsAgo == 1) "Vor 1 Jahr" else "Vor ${it.yearsAgo} Jahren"
    } ?: "Willkommen"
    val heroSubtitle = memories.firstOrNull()?.date ?: "Zuletzt aufgenommen"

    // Erster Fokus geht auf die Play/Diashow-Aktion in der Hero
    val heroFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { try { heroFocus.requestFocus() } catch (_: Exception) {} }

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(32.dp),
    ) {
        // ── HERO ───────────────────────────────────────────────────────────
        item {
            HeroBanner(
                photo = heroPhoto,
                title = heroTitle,
                subtitle = heroSubtitle,
                api = api,
                token = token,
                actionFocus = heroFocus,
                onOpen = {
                    if (memories.isNotEmpty()) {
                        val group = memories.first()
                        onPhotoSelected(group.items, 0)
                    } else if (recent.isNotEmpty()) {
                        onPhotoSelected(recent, 0)
                    }
                },
                onSlideshow = onOpenSlideshow,
            )
        }

        // ── Zuletzt hinzugefügt ────────────────────────────────────────────
        if (recent.isNotEmpty()) {
            item {
                RailHeader(
                    title = "Zuletzt hinzugefügt",
                    action = "Alle anzeigen",
                    onAction = onOpenGallery,
                )
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 40.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    itemsIndexed(recent, key = { _, p -> p.id }) { idx, photo ->
                        SmallPhotoTile(
                            photo = photo,
                            api = api,
                            token = token,
                            onClick = { onPhotoSelected(recent, idx) },
                        )
                    }
                }
            }
        }

        // ── Erinnerungen ────────────────────────────────────────────────────
        if (memories.size > 1) {
            item {
                RailHeader(title = "Erinnerungen", action = "Öffnen", onAction = onOpenMemories)
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 40.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    itemsIndexed(memories) { _, group ->
                        MemoryTile(
                            group = group,
                            api = api,
                            token = token,
                            onClick = {
                                if (group.items.isNotEmpty()) onPhotoSelected(group.items, 0)
                            },
                        )
                    }
                }
            }
        }

        // ── Personen ───────────────────────────────────────────────────────
        if (people.isNotEmpty()) {
            item {
                RailHeader(title = "Personen", action = "Alle", onAction = onOpenPeople)
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 40.dp),
                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    itemsIndexed(people) { _, person ->
                        PersonTile(
                            person = person,
                            api = api,
                            token = token,
                            onClick = onOpenPeople,
                        )
                    }
                }
            }
        }

        // ── Alben ───────────────────────────────────────────────────────────
        if (albums.isNotEmpty()) {
            item {
                RailHeader(title = "Alben", action = "Alle", onAction = onOpenAlbums)
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 40.dp),
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    itemsIndexed(albums) { _, album ->
                        AlbumTile(
                            album = album,
                            api = api,
                            token = token,
                            onClick = onOpenAlbums,
                        )
                    }
                }
            }
        }

        // ── Quick-Actions (falls Library leer ist) ─────────────────────────
        if (recent.isEmpty() && albums.isEmpty()) {
            item {
                Column(
                    Modifier.fillMaxWidth().padding(48.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text("✦", color = Accent, fontSize = 48.sp)
                    Text("Bibliothek ist leer", color = OnSurface, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text(
                        "Sobald der Server Fotos gescannt hat, erscheinen sie hier.",
                        color = Muted, fontSize = 14.sp,
                    )
                }
            }
        }
    }
}

// ── Hero ─────────────────────────────────────────────────────────────────────

@Composable
private fun HeroBanner(
    photo: Photo?,
    title: String,
    subtitle: String,
    api: APIClient,
    token: String,
    actionFocus: FocusRequester,
    onOpen: () -> Unit,
    onSlideshow: () -> Unit,
) {
    val ctx = LocalContext.current
    Box(
        Modifier
            .fillMaxWidth()
            .height(340.dp)
            .background(Surface),
    ) {
        // Hintergrundbild (leicht dunkelgemapped)
        if (photo != null) {
            AsyncImage(
                model = ImageRequest.Builder(ctx)
                    .data(api.thumbUrl(photo.id, "large"))
                    .crossfade(true)
                    .build(),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize().graphicsLayer { alpha = 0.55f },
            )
        }
        // Farbverlauf für Lesbarkeit
        Box(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.horizontalGradient(
                        listOf(BgDark.copy(alpha = 0.85f), BgDark.copy(alpha = 0.15f))
                    )
                )
        )
        Box(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        listOf(Color.Transparent, BgDark.copy(alpha = 0.85f))
                    )
                )
        )

        // Textblock links
        Column(
            Modifier
                .align(Alignment.CenterStart)
                .fillMaxWidth(0.55f)
                .padding(start = 40.dp, top = 32.dp, bottom = 32.dp, end = 24.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                subtitle.uppercase(),
                color = Accent,
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 1.6.sp,
            )
            Text(
                title,
                color = OnSurface,
                fontSize = 40.sp,
                fontWeight = FontWeight.Bold,
                lineHeight = 46.sp,
            )
            Text(
                if (photo?.locationName?.isNotBlank() == true) photo.locationName!!
                else "Deine Foto-Sammlung, elegant auf dem großen Schirm.",
                color = Muted, fontSize = 14.sp,
            )

            Spacer(Modifier.height(8.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                HeroButton(
                    label = "Öffnen",
                    icon = Icons.Filled.PlayArrow,
                    primary = true,
                    modifier = Modifier.focusRequester(actionFocus),
                    onClick = onOpen,
                )
                HeroButton(
                    label = "Diashow",
                    icon = Icons.Filled.Slideshow,
                    primary = false,
                    onClick = onSlideshow,
                )
            }
        }
    }
}

@Composable
private fun HeroButton(
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    primary: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val bg = when {
        focused && primary -> Accent
        focused            -> Accent.copy(alpha = 0.3f)
        primary            -> Accent
        else               -> Color.White.copy(alpha = 0.12f)
    }
    val fg = if (primary || focused) Color.White else OnSurface

    Row(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(bg)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onClick(); true } else false
            }
            .padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(icon, null, tint = fg, modifier = Modifier.size(18.dp))
        Text(label, color = fg, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
    }
}

// ── Rail Header ──────────────────────────────────────────────────────────────

@Composable
private fun RailHeader(title: String, action: String?, onAction: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 40.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(title, color = OnSurface, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
        if (action != null) {
            var focused by remember { mutableStateOf(false) }
            Text(
                text = "$action  ›",
                color = if (focused) Accent else Muted,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
                modifier = Modifier
                    .clip(RoundedCornerShape(6.dp))
                    .background(if (focused) Accent.copy(alpha = 0.15f) else Color.Transparent)
                    .onFocusChanged { focused = it.isFocused }
                    .focusable()
                    .onKeyEvent { e ->
                        if (e.type == KeyEventType.KeyDown &&
                            (e.key == Key.DirectionCenter || e.key == Key.Enter)
                        ) { onAction(); true } else false
                    }
                    .padding(horizontal = 10.dp, vertical = 4.dp),
            )
        }
    }
}

// ── Kacheln ───────────────────────────────────────────────────────────────────

@Composable
private fun SmallPhotoTile(
    photo: Photo,
    api: APIClient,
    token: String,
    onClick: () -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val scale by androidx.compose.animation.core.animateFloatAsState(
        targetValue = if (focused) 1.08f else 1f, label = "photoTileScale",
    )
    val ctx = LocalContext.current
    val d = LocalGridDensity.current

    Box(
        Modifier
            .size(width = d.dashPhotoW, height = d.dashPhotoH)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .clip(RoundedCornerShape(10.dp))
            .background(SurfaceHi)
            .border(
                width = if (focused) 3.dp else 0.dp,
                color = if (focused) Accent else Color.Transparent,
                shape = RoundedCornerShape(10.dp),
            )
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onClick(); true } else false
            },
    ) {
        AsyncImage(
            model = ImageRequest.Builder(ctx)
                .data(api.thumbUrl(photo.id, "medium"))
                .crossfade(true)
                .build(),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxSize(),
        )
        if (photo.isVideo) {
            Box(
                Modifier
                    .align(Alignment.Center)
                    .background(Color.Black.copy(alpha = 0.55f), CircleShape)
                    .padding(8.dp),
            ) {
                Icon(Icons.Filled.PlayArrow, null, tint = Color.White, modifier = Modifier.size(20.dp))
            }
        }
    }
}

@Composable
private fun MemoryTile(
    group: MemoryGroup,
    api: APIClient,
    token: String,
    onClick: () -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val scale by androidx.compose.animation.core.animateFloatAsState(
        targetValue = if (focused) 1.06f else 1f, label = "memTileScale",
    )
    val ctx = LocalContext.current
    val cover = group.items.firstOrNull()
    val d = LocalGridDensity.current

    Box(
        Modifier
            .size(width = d.dashMemoryW, height = d.dashMemoryH)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .clip(RoundedCornerShape(12.dp))
            .background(SurfaceHi)
            .border(
                width = if (focused) 3.dp else 0.dp,
                color = if (focused) Accent else Color.Transparent,
                shape = RoundedCornerShape(12.dp),
            )
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onClick(); true } else false
            },
    ) {
        if (cover != null) {
            AsyncImage(
                model = ImageRequest.Builder(ctx)
                    .data(api.thumbUrl(cover.id, "medium"))
                    .crossfade(true)
                    .build(),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        }
        Box(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(alpha = 0.75f)))
                )
        )
        Column(
            Modifier.align(Alignment.BottomStart).padding(12.dp),
        ) {
            Text(
                if (group.yearsAgo == 1) "Vor 1 Jahr" else "Vor ${group.yearsAgo} Jahren",
                color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
            )
            Text("${group.items.size} Fotos", color = Color.White.copy(alpha = 0.8f), fontSize = 11.sp)
        }
    }
}

@Composable
private fun PersonTile(
    person: Person,
    api: APIClient,
    token: String,
    onClick: () -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val scale by androidx.compose.animation.core.animateFloatAsState(
        targetValue = if (focused) 1.08f else 1f, label = "personTileScale",
    )
    val ctx = LocalContext.current
    val d = LocalGridDensity.current

    Column(
        Modifier
            .width(d.dashPersonAvatar + 20.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onClick(); true } else false
            },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(
            Modifier
                .size(d.dashPersonAvatar)
                .clip(CircleShape)
                .border(
                    width = if (focused) 3.dp else 0.dp,
                    color = if (focused) Accent else Color.Transparent,
                    shape = CircleShape,
                )
                .background(SurfaceHi),
        ) {
            AsyncImage(
                model = ImageRequest.Builder(ctx)
                    .data(api.personAvatarUrl(person.id))
                    .crossfade(120)
                    .build(),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        }
        Text(
            person.name,
            color = if (focused) Accent else OnSurface,
            fontSize = 13.sp,
            fontWeight = FontWeight.Medium,
            maxLines = 1,
        )
    }
}

@Composable
private fun AlbumTile(
    album: Album,
    api: APIClient,
    token: String,
    onClick: () -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val scale by androidx.compose.animation.core.animateFloatAsState(
        targetValue = if (focused) 1.06f else 1f, label = "albumTileScale",
    )
    val ctx = LocalContext.current
    val d = LocalGridDensity.current

    Column(
        Modifier
            .width(d.dashAlbumW)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onClick(); true } else false
            },
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 10f)
                .clip(RoundedCornerShape(10.dp))
                .background(SurfaceHi)
                .border(
                    width = if (focused) 3.dp else 0.dp,
                    color = if (focused) Accent else Color.Transparent,
                    shape = RoundedCornerShape(10.dp),
                ),
        ) {
            if (album.coverPhotoId != null) {
                AsyncImage(
                    model = ImageRequest.Builder(ctx)
                        .data(api.thumbUrl(album.coverPhotoId, "medium"))
                        .crossfade(true)
                        .build(),
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
            }
        }
        Spacer(Modifier.height(8.dp))
        Text(album.name, color = OnSurface, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
        Text("${album.photoCount} Fotos", color = Muted, fontSize = 12.sp)
    }
}
