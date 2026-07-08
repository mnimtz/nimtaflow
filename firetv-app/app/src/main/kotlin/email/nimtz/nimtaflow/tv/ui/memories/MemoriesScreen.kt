package email.nimtz.nimtaflow.tv.ui.memories

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.MemoryGroup
import email.nimtz.nimtaflow.tv.api.Photo
import email.nimtz.nimtaflow.tv.ui.gallery.PhotoCard
import email.nimtz.nimtaflow.tv.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun MemoriesScreen(api: APIClient, token: String, onPhotoSelected: (List<Photo>, Int) -> Unit) {
    var groups by remember { mutableStateOf<List<MemoryGroup>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        try {
            groups = withContext(Dispatchers.IO) { api.memories() }
        } catch (_: Exception) { /* show empty state on error */ } finally {
            loading = false
        }
    }

    if (loading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = Accent)
        }
        return
    }

    if (groups.isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("✦", color = Accent, fontSize = 40.sp)
                Text("Keine Erinnerungen heute", color = OnSurface, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text(
                    "Hier erscheinen Fotos, die vor 1, 2, 3 … Jahren an diesem Tag entstanden sind.",
                    color = Muted, fontSize = 14.sp,
                )
            }
        }
        return
    }

    val firstCardFocus = remember { FocusRequester() }
    LaunchedEffect(groups.isNotEmpty()) {
        if (groups.isNotEmpty()) try { firstCardFocus.requestFocus() } catch (_: Exception) {}
    }

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(32.dp),
    ) {
        itemsIndexed(groups, key = { _, g -> g.yearsAgo }) { rowIdx, group ->
            MemoryGroupRow(
                group, api, token, onPhotoSelected,
                firstCardFocus = if (rowIdx == 0) firstCardFocus else null,
            )
        }
    }
}

@Composable
private fun MemoryGroupRow(
    group: MemoryGroup,
    api: APIClient,
    token: String,
    onPhotoSelected: (List<Photo>, Int) -> Unit,
    firstCardFocus: FocusRequester? = null,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        // Header
        Row(
            Modifier.padding(horizontal = 24.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Box(
                Modifier
                    .size(56.dp)
                    .background(
                        brush = androidx.compose.ui.graphics.Brush.linearGradient(
                            listOf(AccentDim, Accent)
                        ),
                        shape = RoundedCornerShape(14.dp),
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        "${group.yearsAgo}",
                        color = androidx.compose.ui.graphics.Color.White,
                        fontSize = 18.sp, fontWeight = FontWeight.Bold,
                    )
                    Text(
                        if (group.yearsAgo == 1) "Jahr" else "Jahre",
                        color = androidx.compose.ui.graphics.Color.White.copy(alpha = 0.85f),
                        fontSize = 9.sp,
                    )
                }
            }
            Column {
                Text(
                    if (group.yearsAgo == 1) "Vor 1 Jahr" else "Vor ${group.yearsAgo} Jahren",
                    color = OnSurface, fontSize = 20.sp, fontWeight = FontWeight.Bold,
                )
                Text(group.date, color = Muted, fontSize = 13.sp)
            }
        }

        // Horizontal photo strip
        LazyRow(
            contentPadding = PaddingValues(horizontal = 24.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            itemsIndexed(group.items, key = { _, p -> p.id }) { idx, photo ->
                val cardMod = Modifier.size(200.dp).let {
                    if (idx == 0 && firstCardFocus != null) it.focusRequester(firstCardFocus) else it
                }
                PhotoCard(
                    photo = photo,
                    api = api,
                    token = token,
                    modifier = cardMod,
                    onClick = { onPhotoSelected(group.items, idx) },
                )
            }
        }
    }
}
