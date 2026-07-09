package email.nimtz.nimtaflow.tv.ui.home

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
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

private val PRIMARY_TABS = listOf(
    TabItem(HomeTab.Home,      Icons.Default.Home,        "Start"),
    TabItem(HomeTab.Gallery,   Icons.Default.GridView,    "Galerie"),
    TabItem(HomeTab.Favorites, Icons.Default.Favorite,    "Favoriten"),
    TabItem(HomeTab.Albums,    Icons.Default.PhotoAlbum,  "Alben"),
    TabItem(HomeTab.People,    Icons.Default.People,      "Personen"),
    TabItem(HomeTab.Memories,  Icons.Default.AutoAwesome, "Erinnerungen"),
)

private val RAIL_COLLAPSED = 72.dp
private val RAIL_EXPANDED  = 240.dp

/**
 * FireTV Home-Layout — Netflix/Prime-Style Icon-Rail links.
 *
 * Collapsed: 72dp, nur Icons.
 * Expandiert on-focus: 240dp, Icons + Labels.
 * Der Rest der Fläche bleibt für den Content — endlich Platz zum Atmen.
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
    var railFocused by remember { mutableStateOf(false) }
    val railWidth by animateDpAsState(
        targetValue = if (railFocused) RAIL_EXPANDED else RAIL_COLLAPSED,
        animationSpec = tween(220),
        label = "railWidth",
    )
    val railBg by animateColorAsState(
        targetValue = if (railFocused) Surface else Color(0xFF0B0B0F),
        animationSpec = tween(220),
        label = "railBg",
    )

    val firstItemFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        try { firstItemFocus.requestFocus() } catch (_: Exception) {}
    }

    Row(Modifier.fillMaxSize().background(BgDark)) {
        // ── Rail ────────────────────────────────────────────────────────────
        Column(
            Modifier
                .width(railWidth)
                .fillMaxHeight()
                .background(railBg)
                .onFocusChanged { st ->
                    // ganze Column beobachtet Fokus ihrer Kinder
                    railFocused = st.hasFocus
                }
                .padding(vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
            horizontalAlignment = Alignment.Start,
        ) {
            // Logo — kompakt
            RailLogo(expanded = railFocused)
            Spacer(Modifier.height(20.dp))

            PRIMARY_TABS.forEachIndexed { idx, item ->
                RailItem(
                    icon = item.icon,
                    label = item.label,
                    selected = selectedTab == item.tab,
                    expanded = railFocused,
                    onClick = { onTabSelect(item.tab) },
                    modifier = if (idx == 0) Modifier.focusRequester(firstItemFocus) else Modifier,
                )
            }

            Spacer(Modifier.height(20.dp))
            HorizontalDivider(
                color = SurfaceHi.copy(alpha = 0.4f),
                thickness = 1.dp,
                modifier = Modifier.padding(horizontal = 20.dp),
            )
            Spacer(Modifier.height(8.dp))

            // Update — nur wenn verfügbar
            updateRelease?.let { _ ->
                if (updateProgress in 0..100) {
                    if (railFocused) {
                        Column(Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
                            Text("Update wird geladen…", color = Accent, fontSize = 11.sp)
                            Spacer(Modifier.height(6.dp))
                            LinearProgressIndicator(
                                progress = { updateProgress / 100f },
                                modifier = Modifier.fillMaxWidth(),
                                color = Accent,
                                trackColor = SurfaceHi,
                            )
                        }
                    }
                } else {
                    RailItem(
                        icon = Icons.Default.SystemUpdate,
                        label = "Update",
                        selected = false,
                        expanded = railFocused,
                        accent = true,
                        onClick = onInstallUpdate,
                    )
                }
            }

            RailItem(
                icon = Icons.Default.Settings,
                label = "Einstellungen",
                selected = selectedTab == HomeTab.Settings,
                expanded = railFocused,
                onClick = { onTabSelect(HomeTab.Settings) },
            )

            RailItem(
                icon = Icons.AutoMirrored.Filled.Logout,
                label = "Abmelden",
                selected = false,
                expanded = railFocused,
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
private fun RailLogo(expanded: Boolean) {
    Row(
        Modifier.padding(start = 20.dp, end = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(
            Modifier
                .size(32.dp)
                .background(
                    Brush.linearGradient(listOf(AccentDim, Accent)),
                    RoundedCornerShape(9.dp),
                ),
            contentAlignment = Alignment.Center,
        ) {
            Text("✦", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
        }
        if (expanded) {
            Text("NimtaFlow", color = OnSurface, fontSize = 17.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun RailItem(
    icon: ImageVector,
    label: String,
    selected: Boolean,
    expanded: Boolean,
    onClick: () -> Unit,
    accent: Boolean = false,
    modifier: Modifier = Modifier,
) {
    var focused by remember { mutableStateOf(false) }

    val bg = when {
        focused           -> Accent.copy(alpha = 0.20f)
        selected          -> AccentDim.copy(alpha = 0.18f)
        else              -> Color.Transparent
    }
    val tint = when {
        accent && !selected && !focused -> Accent
        selected                        -> Accent
        focused                         -> Accent
        else                            -> Muted
    }

    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 3.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(bg)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onClick(); true } else false
            }
            .padding(horizontal = 12.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // Selected-Indicator: linker vertikaler Balken
        if (selected) {
            Box(
                Modifier
                    .width(3.dp)
                    .height(20.dp)
                    .background(Accent, RoundedCornerShape(2.dp)),
            )
        }
        Icon(icon, contentDescription = label, tint = tint, modifier = Modifier.size(22.dp))
        if (expanded) {
            Text(
                label,
                color = tint,
                fontSize = 14.sp,
                fontWeight = if (selected || focused) FontWeight.SemiBold else FontWeight.Normal,
            )
        }
    }
}
