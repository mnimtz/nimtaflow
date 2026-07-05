package email.nimtz.nimtaflow.tv.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.key.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import email.nimtz.nimtaflow.tv.ui.theme.*

private data class Tile(val tab: HomeTab, val icon: ImageVector, val label: String)

private val TILES = listOf(
    Tile(HomeTab.Gallery,   Icons.Default.GridView,    "Galerie"),
    Tile(HomeTab.Albums,    Icons.Default.PhotoAlbum,  "Alben"),
    Tile(HomeTab.People,    Icons.Default.People,      "Personen"),
    Tile(HomeTab.Memories,  Icons.Default.AutoAwesome, "Erinnerungen"),
    Tile(HomeTab.Favorites, Icons.Default.Favorite,    "Favoriten"),
)

@Composable
fun DashboardScreen(onNavigate: (HomeTab) -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(48.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            "Willkommen",
            color = Muted,
            fontSize = 20.sp,
            fontWeight = FontWeight.Light,
        )
        Text(
            "NimtaFlow",
            color = Accent,
            fontSize = 44.sp,
            fontWeight = FontWeight.Bold,
        )

        Spacer(Modifier.height(32.dp))

        LazyVerticalGrid(
            columns = GridCells.Fixed(3),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            items(TILES, key = { it.tab }) { tile ->
                DashboardTile(
                    icon = tile.icon,
                    label = tile.label,
                    onClick = { onNavigate(tile.tab) },
                )
            }
        }
    }
}

@Composable
private fun DashboardTile(icon: ImageVector, label: String, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .aspectRatio(1.6f)
            .clip(RoundedCornerShape(16.dp))
            .background(if (focused) AccentDim.copy(alpha = 0.35f) else Surface)
            .border(
                width = if (focused) 2.dp else 1.dp,
                color = if (focused) Accent else SurfaceHi,
                shape = RoundedCornerShape(16.dp),
            )
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onClick(); true } else false
            }
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            icon,
            contentDescription = label,
            tint = if (focused) Accent else OnSurface,
            modifier = Modifier.size(44.dp),
        )
        Spacer(Modifier.height(12.dp))
        Text(
            label,
            color = if (focused) Accent else OnSurface,
            fontSize = 16.sp,
            fontWeight = if (focused) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}
