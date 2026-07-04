package email.nimtz.nimtaflow.tv.ui.people

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
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
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
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
import email.nimtz.nimtaflow.tv.ui.gallery.PhotoCard
import email.nimtz.nimtaflow.tv.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun PeopleScreen(
    api: APIClient,
    token: String,
    onPhotoSelected: (List<Photo>, Int) -> Unit,
) {
    var persons by remember { mutableStateOf<List<Person>>(emptyList()) }
    var selectedPerson by remember { mutableStateOf<Person?>(null) }
    var personPhotos by remember { mutableStateOf<List<Photo>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var personLoading by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        persons = withContext(Dispatchers.IO) { api.persons() }
        loading = false
    }

    LaunchedEffect(selectedPerson) {
        val p = selectedPerson ?: return@LaunchedEffect
        personLoading = true
        personPhotos = withContext(Dispatchers.IO) {
            api.photos(personId = p.id, limit = 200).items
        }
        personLoading = false
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

        selectedPerson == null -> PersonGrid(persons, api, token, onSelect = { selectedPerson = it })

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
    persons: List<Person>,
    api: APIClient,
    token: String,
    onSelect: (Person) -> Unit,
) {
    LazyVerticalGrid(
        columns = GridCells.Adaptive(180.dp),
        contentPadding = PaddingValues(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        horizontalArrangement = Arrangement.spacedBy(16.dp),
        modifier = Modifier.fillMaxSize(),
    ) {
        items(persons, key = { it.id }) { person ->
            PersonCard(person, api, token, onClick = { onSelect(person) })
        }
    }
}

@Composable
private fun PersonCard(person: Person, api: APIClient, token: String, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val ctx = LocalContext.current

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier
            .clip(RoundedCornerShape(16.dp))
            .border(2.dp, if (focused) Accent else Color.Transparent, RoundedCornerShape(16.dp))
            .background(if (focused) SurfaceHi else Surface)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)) { onClick(); true } else false
            }
            .padding(16.dp),
    ) {
        // Face thumbnail (circle)
        Box(
            Modifier
                .size(120.dp)
                .clip(CircleShape)
                .background(SurfaceHi),
            contentAlignment = Alignment.Center,
        ) {
            if (person.samplePhotoId != null) {
                AsyncImage(
                    model = ImageRequest.Builder(ctx)
                        .data(api.thumbUrl(person.samplePhotoId, "medium"))
                        .addHeader("Authorization", "Bearer $token")
                        .crossfade(true)
                        .build(),
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
            } else {
                Icon(Icons.Default.Person, null, tint = Muted, modifier = Modifier.size(48.dp))
            }
        }

        Text(
            person.name.ifBlank { "Unbekannt" },
            color = OnSurface,
            fontSize = 15.sp,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Text(
            "${person.photoCount} Fotos",
            color = Muted,
            fontSize = 13.sp,
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
            LazyVerticalGrid(
                columns = GridCells.Adaptive(220.dp),
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
