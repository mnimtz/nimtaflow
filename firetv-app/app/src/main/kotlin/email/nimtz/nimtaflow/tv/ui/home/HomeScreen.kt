package email.nimtz.nimtaflow.tv.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.key.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import email.nimtz.nimtaflow.tv.ui.theme.*
import email.nimtz.nimtaflow.tv.util.ReleaseInfo

enum class HomeTab { Home, Gallery, Favorites, Albums, People, Memories, Settings }

private data class TabItem(val tab: HomeTab, val icon: ImageVector, val label: String)

private val TABS = listOf(
    TabItem(HomeTab.Home,      Icons.Default.Home,        "Start"),
    TabItem(HomeTab.Gallery,   Icons.Default.GridView,    "Galerie"),
    TabItem(HomeTab.Favorites, Icons.Default.Favorite,    "Favoriten"),
    TabItem(HomeTab.Albums,    Icons.Default.PhotoAlbum,  "Alben"),
    TabItem(HomeTab.People,    Icons.Default.People,      "Personen"),
    TabItem(HomeTab.Memories,  Icons.Default.AutoAwesome, "Erinnerungen"),
)

/**
 * FireTV Home-Layout: Feste Sidebar links (immer sichtbar, 240 dp) + Content rechts.
 *
 * Kein TV-NavigationDrawer — der hatte in 1.0.0 Focus-Bugs (auto-expand,
 * kein initialer Fokus), die zu "Bildschirm reagiert nicht"-Symptomen führten.
 * Statische Sidebar ist deterministisch: D-Pad Right verlässt sie in den Content,
 * D-Pad Left holt ihn zurück.
 */
@Composable
fun HomeScreen(
    selectedTab: HomeTab,
    onTabSelect: (HomeTab) -> Unit,
    onLogout: () -> Unit,
    updateRelease: ReleaseInfo? = null,
    updateProgress: Int = -1,
    onInstallUpdate: () -> Unit = {},
    content: @Composable () -> Unit,
) {
    // Initialer Fokus landet auf dem ersten Nav-Item — sonst ist D-Pad tot.
    val firstItemFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        // kurze Verzögerung damit die View sicher in der Composition ist
        try { firstItemFocus.requestFocus() } catch (_: Exception) {}
    }

    Row(Modifier.fillMaxSize().background(BgDark)) {
        // ── Sidebar ────────────────────────────────────────────────────────
        Column(
            Modifier
                .width(240.dp)
                .fillMaxHeight()
                .background(Surface)
                .padding(vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            // Logo
            Row(
                Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Box(
                    Modifier
                        .size(32.dp)
                        .background(
                            Brush.linearGradient(listOf(AccentDim, Accent)),
                            RoundedCornerShape(8.dp),
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("✦", color = Color.White, fontSize = 14.sp)
                }
                Text("NimtaFlow", color = Accent, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            }

            Spacer(Modifier.height(16.dp))

            // Hauptnavigation — erstes Item bekommt den FocusRequester
            TABS.forEachIndexed { idx, item ->
                SidebarItem(
                    icon = item.icon,
                    label = item.label,
                    selected = selectedTab == item.tab,
                    onClick = { onTabSelect(item.tab) },
                    modifier = if (idx == 0) Modifier.focusRequester(firstItemFocus) else Modifier,
                )
            }

            Spacer(Modifier.height(24.dp))
            HorizontalDivider(
                color = SurfaceHi,
                thickness = 1.dp,
                modifier = Modifier.padding(horizontal = 20.dp),
            )
            Spacer(Modifier.height(8.dp))

            // Update-Hinweis
            updateRelease?.let { _ ->
                if (updateProgress in 0..100) {
                    Column(Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
                        Text("Update wird geladen…", color = Accent, fontSize = 12.sp)
                        Spacer(Modifier.height(6.dp))
                        LinearProgressIndicator(
                            progress = { updateProgress / 100f },
                            modifier = Modifier.fillMaxWidth(),
                            color = Accent,
                            trackColor = SurfaceHi,
                        )
                    }
                } else {
                    SidebarItem(
                        icon = Icons.Default.SystemUpdate,
                        label = "Update verfügbar",
                        selected = false,
                        accent = true,
                        onClick = onInstallUpdate,
                    )
                }
            }

            SidebarItem(
                icon = Icons.Default.Settings,
                label = "Einstellungen",
                selected = selectedTab == HomeTab.Settings,
                onClick = { onTabSelect(HomeTab.Settings) },
            )

            SidebarItem(
                icon = Icons.AutoMirrored.Filled.Logout,
                label = "Abmelden",
                selected = false,
                onClick = onLogout,
            )
        }

        // ── Content ────────────────────────────────────────────────────────
        Box(Modifier.weight(1f).fillMaxHeight().background(BgDark)) {
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
    accent: Boolean = false,
    modifier: Modifier = Modifier,
) {
    var focused by remember { mutableStateOf(false) }

    val bg = when {
        focused && selected -> Accent.copy(alpha = 0.35f)
        focused             -> SurfaceHi
        selected            -> AccentDim.copy(alpha = 0.20f)
        else                -> Color.Transparent
    }
    val contentColor = when {
        accent   -> Accent
        selected -> Accent
        focused  -> OnSurface
        else     -> Muted
    }

    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 2.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(bg)
            .border(
                width = if (focused) 1.dp else 0.dp,
                color = if (focused) Accent else Color.Transparent,
                shape = RoundedCornerShape(8.dp),
            )
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onClick(); true } else false
            }
            .padding(horizontal = 12.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Icon(icon, contentDescription = label, tint = contentColor, modifier = Modifier.size(22.dp))
        Text(
            label,
            color = contentColor,
            fontSize = 15.sp,
            fontWeight = if (selected || focused) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}
