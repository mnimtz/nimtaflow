package email.nimtz.nimtaflow.tv.ui.albums

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Album
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.ui.gallery.PhotoCard
import email.nimtz.nimtaflow.tv.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun AlbumsScreen(api: APIClient, token: String, onPhotoSelected: (List<Photo>, Int) -> Unit) {
    var albums by remember { mutableStateOf<List<Album>>(emptyList()) }
    var selectedAlbum by remember { mutableStateOf<Album?>(null) }
    var albumPhotos by remember { mutableStateOf<List<Photo>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        try {
            albums = withContext(Dispatchers.IO) { api.albums() }
        } catch (_: Exception) { /* show empty list on error */ } finally {
            loading = false
        }
    }

    LaunchedEffect(selectedAlbum) {
        val alb = selectedAlbum ?: return@LaunchedEffect
        try {
            albumPhotos = withContext(Dispatchers.IO) { api.albumPhotos(alb.id).items }
        } catch (_: Exception) { albumPhotos = emptyList() }
    }

    if (loading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = Accent)
        }
        return
    }

    if (selectedAlbum == null) {
        // Album grid
        LazyVerticalGrid(
            columns = GridCells.Adaptive(260.dp),
            contentPadding = PaddingValues(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            modifier = Modifier.fillMaxSize(),
        ) {
            items(albums, key = { it.id }) { album ->
                AlbumCard(album, api, token, onClick = { selectedAlbum = album })
            }
        }
    } else {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.padding(20.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                TextButton(onClick = { selectedAlbum = null; albumPhotos = emptyList() }) {
                    Text("← Alben", color = Accent)
                }
                Text(selectedAlbum!!.name, color = OnSurface, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            }
            LazyVerticalGrid(
                columns = GridCells.Adaptive(220.dp),
                contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                itemsIndexed(albumPhotos, key = { _, p -> p.id }) { idx, photo ->
                    PhotoCard(photo, api, token,
                        onClick = { onPhotoSelected(albumPhotos, idx) })
                }
            }
        }
    }
}

@Composable
private fun AlbumCard(album: Album, api: APIClient, token: String, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val ctx = LocalContext.current

    Column(
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .border(2.dp, if (focused) Accent else Color.Transparent, RoundedCornerShape(12.dp))
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)) { onClick(); true } else false
            },
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f)
                .background(SurfaceHi),
        ) {
            if (album.coverPhotoId != null) {
                AsyncImage(
                    model = ImageRequest.Builder(ctx)
                        .data(api.thumbUrl(album.coverPhotoId, "medium"))
                        .addHeader("Authorization", "Bearer $token")
                        .crossfade(true)
                        .build(),
                    contentDescription = null,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
            }
        }
        Column(
            Modifier.background(Surface).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Text(album.name, color = OnSurface, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text("${album.photoCount} Fotos", color = Muted, fontSize = 13.sp)
        }
    }
}
