package email.nimtz.nimtaflow.tv.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import email.nimtz.nimtaflow.tv.ui.theme.*

enum class HomeTab { Gallery, Favorites, Albums, Memories }

private data class TabItem(val tab: HomeTab, val icon: ImageVector, val label: String)

private val TABS = listOf(
    TabItem(HomeTab.Gallery,   Icons.Default.GridView,    "Galerie"),
    TabItem(HomeTab.Favorites, Icons.Default.Favorite,    "Favoriten"),
    TabItem(HomeTab.Albums,    Icons.Default.PhotoAlbum,  "Alben"),
    TabItem(HomeTab.Memories,  Icons.Default.AutoAwesome, "Erinnerungen"),
)

/**
 * Persistent left sidebar + content area.
 * D-pad LEFT/RIGHT switches focus between sidebar and content.
 */
@Composable
fun HomeScreen(
    selectedTab: HomeTab,
    onTabSelect: (HomeTab) -> Unit,
    onLogout: () -> Unit,
    content: @Composable () -> Unit,
) {
    Row(Modifier.fillMaxSize().background(BgDark)) {

        // ── Left sidebar ──────────────────────────────────────────────────────
        Column(
            Modifier
                .width(200.dp)
                .fillMaxHeight()
                .background(Surface)
                .padding(vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                "✦ NimtaFlow",
                color = Accent, fontSize = 18.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
            )
            Spacer(Modifier.height(12.dp))

            TABS.forEach { item ->
                SidebarItem(
                    icon = item.icon,
                    label = item.label,
                    selected = selectedTab == item.tab,
                    onClick = { onTabSelect(item.tab) },
                )
            }

            Spacer(Modifier.weight(1f))

            SidebarItem(
                icon = Icons.Default.Logout,
                label = "Abmelden",
                selected = false,
                onClick = onLogout,
            )
        }

        // ── Content area ─────────────────────────────────────────────────────
        Box(Modifier.weight(1f).fillMaxHeight()) {
            content()
        }
    }
}

@Composable
private fun SidebarItem(
    icon: ImageVector,
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val bg = when {
        selected -> AccentDim.copy(alpha = 0.25f)
        focused  -> SurfaceHi
        else     -> Color.Transparent
    }
    val fg = if (selected || focused) OnSurface else Muted

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp)
            .background(bg, RoundedCornerShape(8.dp))
            .selectable(selected = selected, onClick = onClick)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(icon, contentDescription = null, tint = if (selected) Accent else fg, modifier = Modifier.size(20.dp))
        Text(label, color = fg, fontSize = 15.sp,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal)
    }
}
