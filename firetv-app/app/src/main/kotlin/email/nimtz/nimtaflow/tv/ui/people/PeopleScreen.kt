package email.nimtz.nimtaflow.tv.ui.people

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Person
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Person
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.ui.LocalGridDensity
import email.nimtz.nimtaflow.tv.ui.LocalPeopleSort
import email.nimtz.nimtaflow.tv.ui.PeopleSort
import email.nimtz.nimtaflow.tv.ui.gallery.PhotoCard
import email.nimtz.nimtaflow.tv.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun PeopleScreen(
    api: APIClient,
    token: String,
    isAdmin: Boolean = false,
    onPhotoSelected: (List<Photo>, Int) -> Unit,
) {
    var persons by remember { mutableStateOf<List<Person>>(emptyList()) }
    var selectedPerson by remember { mutableStateOf<Person?>(null) }
    var personPhotos by remember { mutableStateOf<List<Photo>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var personLoading by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        try {
            persons = withContext(Dispatchers.IO) { api.persons() }
        } catch (_: Exception) { /* show empty list on error */ } finally {
            loading = false
        }
    }

    LaunchedEffect(selectedPerson) {
        val p = selectedPerson ?: return@LaunchedEffect
        personLoading = true
        try {
            personPhotos = withContext(Dispatchers.IO) {
                api.photos(personId = p.id, limit = 200).items
            }
        } catch (_: Exception) {
            personPhotos = emptyList()
        } finally {
            personLoading = false
        }
    }

    when {
        loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = Accent)
        }

        persons.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(Icons.Default.Person, null, tint = Accent, modifier = Modifier.size(48.dp))
                Text("Keine Personen erkannt", color = OnSurface, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("Gesichtserkennung läuft im Hintergrund.", color = Muted, fontSize = 14.sp)
            }
        }

        selectedPerson == null -> {
            val sort = LocalPeopleSort.current
            val named = persons.filter { it.name.isNotBlank() }.let { list ->
                when (sort) {
                    PeopleSort.ByPhotoCount ->
                        list.sortedWith(compareByDescending<Person> { it.photoCount }.thenBy { it.name.lowercase() })
                    PeopleSort.ByName ->
                        list.sortedBy { it.name.lowercase() }
                }
            }
            val unknown = if (isAdmin)
                persons.filter { it.name.isBlank() }.sortedByDescending { it.photoCount }
            else emptyList()
            PersonGrid(
                named = named,
                unknown = unknown,
                api = api,
                token = token,
                onSelect = { selectedPerson = it },
            )
        }

        else -> PersonPhotos(
            person = selectedPerson!!,
            photos = personPhotos,
            loading = personLoading,
            api = api,
            token = token,
            onBack = { selectedPerson = null; personPhotos = emptyList() },
            onPhotoSelected = onPhotoSelected,
        )
    }
}

// ── Person grid ───────────────────────────────────────────────────────────────

@Composable
private fun PersonGrid(
    named: List<Person>,
    unknown: List<Person>,
    api: APIClient,
    token: String,
    onSelect: (Person) -> Unit,
) {
    val firstPersonFocus = remember { FocusRequester() }
    LaunchedEffect(named.isNotEmpty() || unknown.isNotEmpty()) {
        if (named.isNotEmpty() || unknown.isNotEmpty())
            try { firstPersonFocus.requestFocus() } catch (_: Exception) {}
    }

    val density = LocalGridDensity.current
    LazyVerticalGrid(
        columns = GridCells.Adaptive(density.personCellMin),
        contentPadding = PaddingValues(24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        modifier = Modifier.fillMaxSize(),
    ) {
        itemsIndexed(named, key = { _, p -> p.id }) { idx, person ->
            PersonCard(
                person, api, token,
                onClick = { onSelect(person) },
                modifier = if (idx == 0) Modifier.focusRequester(firstPersonFocus) else Modifier,
            )
        }

        if (unknown.isNotEmpty()) {
            item(span = { GridItemSpan(maxLineSpan) }) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 16.dp, bottom = 4.dp),
                ) {
                    Text(
                        "Unbekannte Personen",
                        color = Muted,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(end = 8.dp),
                    )
                    Text(
                        "(${unknown.size})",
                        color = Muted.copy(alpha = 0.6f),
                        fontSize = 13.sp,
                    )
                    Spacer(Modifier.weight(1f))
                    HorizontalDivider(
                        modifier = Modifier.weight(3f),
                        color = Muted.copy(alpha = 0.25f),
                    )
                }
            }
            items(unknown, key = { it.id }) { person ->
                PersonCard(person, api, token, onClick = { onSelect(person) })
            }
        }
    }
}

@Composable
private fun PersonCard(
    person: Person,
    api: APIClient,
    token: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var focused by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    val density = LocalGridDensity.current
    val scale by androidx.compose.animation.core.animateFloatAsState(
        targetValue = if (focused) 1.06f else 1f, label = "personCardScale",
    )

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
        modifier = modifier
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .clip(RoundedCornerShape(18.dp))
            .background(if (focused) SurfaceHi else Surface)
            .border(
                width = if (focused) 2.dp else 1.dp,
                color = if (focused) Accent else SurfaceHi.copy(alpha = 0.4f),
                shape = RoundedCornerShape(18.dp),
            )
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)) { onClick(); true } else false
            }
            .padding(density.personCardPad),
    ) {
        // Face thumbnail (circle)
        Box(
            Modifier
                .size(density.personAvatar)
                .clip(CircleShape)
                .background(SurfaceHi),
            contentAlignment = Alignment.Center,
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
            person.name.ifBlank { "Unbekannt" },
            color = if (focused) Accent else OnSurface,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            "${person.photoCount} Fotos",
            color = Muted,
            fontSize = 11.sp,
            textAlign = TextAlign.Center,
        )
    }
}

// ── Person photo grid ─────────────────────────────────────────────────────────

@Composable
private fun PersonPhotos(
    person: Person,
    photos: List<Photo>,
    loading: Boolean,
    api: APIClient,
    token: String,
    onBack: () -> Unit,
    onPhotoSelected: (List<Photo>, Int) -> Unit,
) {
    Column(Modifier.fillMaxSize()) {
        // Header
        Row(
            Modifier.padding(horizontal = 20.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            TextButton(onClick = onBack) {
                Text("← Personen", color = Accent, fontSize = 14.sp)
            }
            Text(
                person.name.ifBlank { "Unbekannt" },
                color = OnSurface,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
            )
            Text("· ${person.photoCount} Fotos", color = Muted, fontSize = 14.sp)
        }

        if (loading) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = Accent)
            }
        } else {
            val density = LocalGridDensity.current
            LazyVerticalGrid(
                columns = GridCells.Adaptive(density.galleryCellMin),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                itemsIndexed(photos, key = { _, p -> p.id }) { idx, photo ->
                    PhotoCard(photo, api, token, onClick = { onPhotoSelected(photos, idx) })
                }
            }
        }
    }
}
