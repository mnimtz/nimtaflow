package email.nimtz.nimtaflow.tv.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.tv.material3.DrawerValue
import androidx.tv.material3.NavigationDrawer
import androidx.tv.material3.NavigationDrawerItem
import androidx.tv.material3.NavigationDrawerItemDefaults
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
    NavigationDrawer(
        drawerContent = {
            // Logo — nur wenn Drawer offen
            if (currentValue == DrawerValue.Open) {
                Row(
                    Modifier.padding(horizontal = 20.dp, vertical = 16.dp),
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
                    Text(
                        "NimtaFlow",
                        color = Accent,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            } else {
                Spacer(Modifier.height(24.dp))
            }

            // Hauptnavigation
            TABS.forEach { item ->
                NavigationDrawerItem(
                    selected = selectedTab == item.tab,
                    onClick = { onTabSelect(item.tab) },
                    leadingContent = {
                        Icon(
                            item.icon,
                            contentDescription = item.label,
                            tint = if (selectedTab == item.tab) Accent else Muted,
                        )
                    },
                    colors = NavItemColors,
                ) {
                    Text(
                        item.label,
                        color = if (selectedTab == item.tab) Accent else OnSurface,
                        fontWeight = if (selectedTab == item.tab) FontWeight.SemiBold else FontWeight.Normal,
                    )
                }
            }

            Spacer(Modifier.weight(1f))

            HorizontalDivider(
                color = SurfaceHi,
                thickness = 1.dp,
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            )

            // Update-Hinweis als Nav-Item
            updateRelease?.let { release ->
                if (updateProgress in 0..100) {
                    // Fortschrittsanzeige während Download
                    Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                        Text("Herunterladen…", color = Accent, fontSize = 12.sp)
                        Spacer(Modifier.height(4.dp))
                        LinearProgressIndicator(
                            progress = { updateProgress / 100f },
                            modifier = Modifier.fillMaxWidth(),
                            color = Accent,
                            trackColor = SurfaceHi,
                        )
                    }
                } else {
                    NavigationDrawerItem(
                        selected = false,
                        onClick = onInstallUpdate,
                        leadingContent = {
                            Icon(Icons.Default.SystemUpdate, null, tint = Accent)
                        },
                        colors = NavItemColors,
                    ) {
                        Text(
                            "Update verfügbar",
                            color = Accent,
                            fontWeight = FontWeight.Medium,
                            fontSize = 13.sp,
                        )
                    }
                }
            }

            NavigationDrawerItem(
                selected = selectedTab == HomeTab.Settings,
                onClick = { onTabSelect(HomeTab.Settings) },
                leadingContent = {
                    Icon(Icons.Default.Settings, null, tint = Muted)
                },
                colors = NavItemColors,
            ) {
                Text("Einstellungen", color = OnSurface)
            }

            NavigationDrawerItem(
                selected = false,
                onClick = onLogout,
                leadingContent = {
                    Icon(Icons.Default.Logout, null, tint = Muted)
                },
                colors = NavItemColors,
            ) {
                Text("Abmelden", color = Muted)
            }

            Spacer(Modifier.height(16.dp))
        },
    ) {
        Box(Modifier.fillMaxSize().background(BgDark)) {
            content()
        }
    }
}

// Angepasste Farben für NavigationDrawerItem auf dunklem Hintergrund
private val NavItemColors
    @Composable get() = NavigationDrawerItemDefaults.colors(
        selectedContainerColor   = AccentDim.copy(alpha = 0.25f),
        focusedContainerColor    = SurfaceHi,
        containerColor           = Color.Transparent,
        contentColor             = OnSurface,
        focusedContentColor      = OnSurface,
        selectedContentColor     = Accent,
        pressedContainerColor    = SurfaceHi,
    )
