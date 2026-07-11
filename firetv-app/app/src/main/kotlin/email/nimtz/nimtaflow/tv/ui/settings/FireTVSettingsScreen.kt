package email.nimtz.nimtaflow.tv.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Album
import email.nimtz.nimtaflow.tv.api.Person
import email.nimtz.nimtaflow.tv.screensaver.ScreensaverPrefs
import email.nimtz.nimtaflow.tv.ui.GridDensity
import email.nimtz.nimtaflow.tv.ui.PeopleSort
import email.nimtz.nimtaflow.tv.ui.theme.*
import email.nimtz.nimtaflow.tv.util.ReleaseInfo
import email.nimtz.nimtaflow.tv.util.UpdateChecker
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*

private data class AdbDevice(val id: String, val model: String, val state: String)

/**
 * Einstellungen. Aufräumt: nur noch drei Karten (App, Bildschirmschoner, Update).
 * ADB-Sektion nur wenn User Admin ist (holt sich sonst nicht viel Sinn).
 */
@Composable
fun FireTVSettingsScreen(api: APIClient) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val prefs = (context.applicationContext as email.nimtz.nimtaflow.tv.NimtaFlowApp).prefs
    val isAdmin by prefs.isAdmin.collectAsState(initial = false)

    val versionName = remember {
        try { context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "?" }
        catch (_: Exception) { "?" }
    }
    val serverUrl by prefs.serverUrl.collectAsState(initial = "")

    var autoUpdate by remember { mutableStateOf(false) }
    var checkResult by remember { mutableStateOf<String?>(null) }
    var checking by remember { mutableStateOf(false) }
    var latestRelease by remember { mutableStateOf<ReleaseInfo?>(null) }
    var updateProgress by remember { mutableStateOf(-1) }
    val lastInstalled by prefs.lastInstalledRelease.collectAsState(initial = "")

    LaunchedEffect(Unit) {
        try {
            val s = api.getJson("api/settings")
            autoUpdate = s["firetv.auto_update"]?.jsonPrimitive?.content == "true"
        } catch (_: Exception) {}
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(BgDark)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 40.dp, vertical = 32.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        Text("Einstellungen", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = OnSurface)

        // ── Diese App ────────────────────────────────────────────────────────
        SettingsCard("Diese App") {
            InfoRow(Icons.Filled.Info, "Version", "NimtaFlow TV $versionName")
            InfoRow(Icons.Filled.Cloud, "Server", serverUrl.ifBlank { "Nicht verbunden" })
        }

        // ── Ansicht (Grid-Dichte + Sortierung) ──────────────────────────────
        val densityId by prefs.gridDensity.collectAsState(initial = "medium")
        val peopleSortId by prefs.peopleSort.collectAsState(initial = "count")
        SettingsCard("Ansicht") {
            SectionLabel("Grid-Dichte (alle Ansichten)")
            SegmentedPicker(
                options = GridDensity.entries.map { it.id to it.label },
                selected = densityId,
                onSelect = { id -> scope.launch { prefs.saveGridDensity(id) } },
            )
            Text(
                GridDensity.fromId(densityId).hint,
                color = Muted, fontSize = 12.sp,
            )
            Spacer(Modifier.height(8.dp))
            SectionLabel("Personen sortieren nach")
            SegmentedPicker(
                options = PeopleSort.entries.map { it.id to when (it) {
                    PeopleSort.ByPhotoCount -> "Fotoanzahl"
                    PeopleSort.ByName       -> "Alphabetisch"
                } },
                selected = peopleSortId,
                onSelect = { id -> scope.launch { prefs.savePeopleSort(id) } },
            )
        }

        // ── Bildschirmschoner ────────────────────────────────────────────────
        ScreensaverSettingsCard(api)

        // ── Update ───────────────────────────────────────────────────────────
        SettingsCard("App-Update") {
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("Auto-Update", color = OnSurface, fontSize = 15.sp)
                    Text(
                        "Prüft täglich auf neue App-Versionen",
                        color = Muted, fontSize = 12.sp,
                    )
                }
                Switch(
                    checked = autoUpdate,
                    onCheckedChange = { v ->
                        autoUpdate = v
                        scope.launch {
                            try { api.patchSettings(mapOf("firetv.auto_update" to if (v) "true" else "false")) }
                            catch (_: Exception) {}
                        }
                    },
                    colors = SwitchDefaults.colors(checkedThumbColor = Accent, checkedTrackColor = AccentDim),
                )
            }

            FocusableButton(
                text = if (checking) "Prüfen…" else "Jetzt nach Updates suchen",
                icon = Icons.Filled.Refresh,
                enabled = !checking && updateProgress < 0,
                onClick = {
                    scope.launch {
                        checking = true; checkResult = null
                        try {
                            val release = UpdateChecker.fetchLatestRelease()
                            if (release != null) {
                                latestRelease = release
                                val newer = UpdateChecker.isNewer(release.publishedAt, lastInstalled)
                                checkResult = if (newer) "Update verfügbar: ${release.releaseName}"
                                              else "App ist aktuell"
                            } else checkResult = "Kein Release gefunden"
                        } catch (_: Exception) { checkResult = "Fehler beim Prüfen" }
                        finally { checking = false }
                    }
                },
            )

            latestRelease?.let { release ->
                if (UpdateChecker.isNewer(release.publishedAt, lastInstalled)) {
                    FocusableButton(
                        text = "Update installieren",
                        icon = Icons.Filled.Download,
                        enabled = updateProgress < 0,
                        primary = true,
                        onClick = {
                            scope.launch {
                                updateProgress = 0
                                try {
                                    UpdateChecker.downloadAndInstall(
                                        context = context,
                                        downloadUrl = release.downloadUrl,
                                        onProgress = { updateProgress = it },
                                    )
                                    prefs.saveLastInstalledRelease(release.publishedAt)
                                } catch (_: Exception) {} finally { updateProgress = -1 }
                            }
                        },
                    )
                }
            }

            if (updateProgress in 0..100) {
                LinearProgressIndicator(
                    progress = { updateProgress / 100f },
                    modifier = Modifier.fillMaxWidth(),
                    color = Accent,
                    trackColor = SurfaceHi,
                )
                Text("Herunterladen… $updateProgress %", color = Muted, fontSize = 12.sp)
            }

            checkResult?.let { Text(it, color = Muted, fontSize = 13.sp) }
        }

        // ── Admin-Sektion: App auf weiteren FireTVs verteilen ────────────────
        if (isAdmin) {
            AdminAdbSection(api)
        }
    }
}

@Composable
private fun AdminAdbSection(api: APIClient) {
    val scope = rememberCoroutineScope()
    var adbDevices by remember { mutableStateOf<List<AdbDevice>>(emptyList()) }
    var scanning by remember { mutableStateOf(false) }
    var installing by remember { mutableStateOf<String?>(null) }
    var installMsg by remember { mutableStateOf<String?>(null) }

    SettingsCard("Weitere FireTV im Netzwerk (Admin)") {
        Text(
            "Verteilt diese App per ADB an andere FireTVs im WLAN. " +
            "Am Zielgerät müssen Entwickleroptionen + ADB über Netzwerk aktiv sein.",
            color = Muted, fontSize = 13.sp,
        )

        FocusableButton(
            text = if (scanning) "Suche…" else "Geräte suchen",
            icon = Icons.Filled.Wifi,
            enabled = !scanning,
            onClick = {
                scope.launch {
                    scanning = true; adbDevices = emptyList(); installMsg = null
                    try {
                        val subnetParam = run {
                            val m = Regex("""(?:https?://)(\d+\.\d+\.\d+)\.\d+""").find(api.baseUrl)
                            m?.groupValues?.get(1)?.let { "?subnet=$it" } ?: ""
                        }
                        val result = api.getJson("api/v1/software/firetv/adb-devices$subnetParam")
                        val list = result["devices"]?.jsonArray ?: JsonArray(emptyList())
                        adbDevices = list.mapNotNull { el ->
                            val obj = el.jsonObject
                            val id    = obj["id"]?.jsonPrimitive?.content ?: return@mapNotNull null
                            val model = obj["model"]?.jsonPrimitive?.content ?: id
                            val state = obj["state"]?.jsonPrimitive?.content ?: "?"
                            AdbDevice(id, model, state)
                        }
                        if (adbDevices.isEmpty()) installMsg = "Keine Geräte gefunden"
                    } catch (_: Exception) { installMsg = "Scan fehlgeschlagen" }
                    finally { scanning = false }
                }
            },
        )

        adbDevices.forEach { device ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(BgDark, RoundedCornerShape(8.dp))
                    .padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(device.model, color = OnSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                    Text(device.id, color = Muted, fontSize = 12.sp)
                }
                FocusableButton(
                    text = if (installing == device.id) "…" else "Installieren",
                    enabled = installing == null,
                    primary = true,
                    onClick = {
                        scope.launch {
                            installing = device.id
                            installMsg = null
                            try {
                                val resp = api.postJson(
                                    "api/v1/software/firetv/adb-install",
                                    buildJsonObject { put("device_id", device.id) }
                                )
                                val status = resp["status"]?.jsonPrimitive?.content ?: "installed"
                                val message = resp["message"]?.jsonPrimitive?.content
                                installMsg = when (status) {
                                    "installed"    -> "✓ ${device.model}: App installiert"
                                    "reinstalled"  -> "✓ ${device.model}: neu installiert (Signatur-Konflikt aufgelöst)"
                                    "unauthorized" -> message ?: "FireTV: USB-Debugging noch nicht bestätigt"
                                    "offline"      -> message ?: "${device.model} nicht erreichbar"
                                    else           -> message ?: "Installation fehlgeschlagen"
                                }
                            } catch (e: Exception) {
                                installMsg = "Installation fehlgeschlagen: ${e.message ?: "unbekannt"}"
                            } finally { installing = null }
                        }
                    },
                )
            }
        }

        installMsg?.let { Text(it, color = Muted, fontSize = 13.sp) }
    }
}

@Composable
private fun ScreensaverSettingsCard(api: APIClient) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val ssPrefs = remember { ScreensaverPrefs(context) }

    val mode by ssPrefs.mode.collectAsState(initial = "all")
    val personRaw by ssPrefs.personIds.collectAsState(initial = "")
    val albumRaw by ssPrefs.albumIds.collectAsState(initial = "")
    val intervalSec by ssPrefs.intervalSec.collectAsState(initial = 10)
    val showInfo by ssPrefs.showInfo.collectAsState(initial = false)

    var persons by remember { mutableStateOf<List<Person>>(emptyList()) }
    var albums by remember { mutableStateOf<List<Album>>(emptyList()) }

    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            runCatching { persons = api.persons() }
            runCatching { albums = api.albums() }
        }
    }

    val selectedPersons = ssPrefs.personIdSet(personRaw)
    val selectedAlbums = ssPrefs.albumIdSet(albumRaw)

    val modes = listOf(
        "all"        to "Alle Fotos",
        "highlights" to "Highlights",
        "persons"    to "Personen",
        "albums"     to "Alben",
    )
    val intervals = listOf(5 to "5 s", 10 to "10 s", 30 to "30 s", 60 to "1 min")

    SettingsCard("Bildschirmschoner") {
        Text(
            "Zeigt Fotos wenn FireTV den Bildschirmschoner startet " +
            "(Einstellungen → Anzeige & Ton → Bildschirmschoner).",
            color = Muted, fontSize = 13.sp,
        )

        SectionLabel("Quelle")
        ChipRowSelectable(
            options = modes.map { it.second },
            selectedIndex = modes.indexOfFirst { it.first == mode }.coerceAtLeast(0),
            onSelect = { idx -> scope.launch { ssPrefs.saveMode(modes[idx].first) } },
        )

        if (mode == "persons" && persons.isNotEmpty()) {
            SectionLabel("Personen auswählen")
            persons.forEach { person ->
                val checked = person.id in selectedPersons
                ToggleRow(
                    label = person.name,
                    checked = checked,
                    onCheckedChange = { on ->
                        val newSet = if (on) selectedPersons + person.id else selectedPersons - person.id
                        scope.launch { ssPrefs.savePersonIds(newSet.joinToString(",")) }
                    },
                )
            }
        }

        if (mode == "albums" && albums.isNotEmpty()) {
            SectionLabel("Alben auswählen")
            albums.forEach { album ->
                val checked = album.id in selectedAlbums
                ToggleRow(
                    label = album.name,
                    hint = "${album.photoCount} Fotos",
                    checked = checked,
                    onCheckedChange = { on ->
                        val newSet = if (on) selectedAlbums + album.id else selectedAlbums - album.id
                        scope.launch { ssPrefs.saveAlbumIds(newSet.joinToString(",")) }
                    },
                )
            }
        }

        SectionLabel("Intervall")
        ChipRowSelectable(
            options = intervals.map { it.second },
            selectedIndex = intervals.indexOfFirst { it.first == intervalSec }.coerceAtLeast(0),
            onSelect = { idx -> scope.launch { ssPrefs.saveIntervalSec(intervals[idx].first) } },
        )

        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("Datum & Ort einblenden", color = OnSurface, fontSize = 15.sp)
            Switch(
                checked = showInfo,
                onCheckedChange = { scope.launch { ssPrefs.saveShowInfo(it) } },
                colors = SwitchDefaults.colors(checkedThumbColor = Accent, checkedTrackColor = AccentDim),
            )
        }
    }
}

// ── Reusable Bits ────────────────────────────────────────────────────────────

@Composable
private fun SettingsCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = Surface,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(
                title.uppercase(),
                color = Accent,
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 1.4.sp,
            )
            content()
        }
    }
}

@Composable
private fun SectionLabel(label: String) {
    Text(label, color = OnSurface, fontSize = 13.sp, fontWeight = FontWeight.Medium)
}

/** Chip-Row: mehrere Werte, fokusierbar; aktueller Wert visuell markiert. */
@Composable
private fun SegmentedPicker(
    options: List<Pair<String, String>>,
    selected: String,
    onSelect: (String) -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { (id, label) ->
            var focused by remember { mutableStateOf(false) }
            val isSel = id == selected
            val bg = when {
                focused && isSel -> Accent
                focused           -> Accent.copy(alpha = 0.28f)
                isSel             -> AccentDim.copy(alpha = 0.4f)
                else              -> SurfaceHi
            }
            val fg = if (isSel || focused) Color.White else OnSurface
            Row(
                Modifier
                    .clip(RoundedCornerShape(10.dp))
                    .background(bg)
                    .onFocusChanged { focused = it.isFocused }
                    .focusable()
                    .onKeyEvent { e ->
                        if (e.type == KeyEventType.KeyDown &&
                            (e.key == Key.DirectionCenter || e.key == Key.Enter)
                        ) { onSelect(id); true } else false
                    }
                    .padding(horizontal = 14.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(label, color = fg, fontSize = 13.sp,
                     fontWeight = if (isSel) FontWeight.SemiBold else FontWeight.Normal)
            }
        }
    }
}

@Composable
private fun InfoRow(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, value: String) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(icon, null, tint = Muted, modifier = Modifier.size(18.dp))
        Text(label, color = Muted, fontSize = 13.sp, modifier = Modifier.weight(1f))
        Text(value, color = OnSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun FocusableButton(
    text: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector? = null,
    enabled: Boolean = true,
    primary: Boolean = false,
    onClick: () -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val baseColor = if (primary) Accent else SurfaceHi
    val bg = when {
        !enabled -> baseColor.copy(alpha = 0.4f)
        focused -> if (primary) AccentDim else Accent.copy(alpha = 0.3f)
        else -> baseColor
    }

    Row(
        Modifier
            .clip(RoundedCornerShape(10.dp))
            .background(bg)
            .onFocusChanged { focused = it.isFocused }
            .focusable(enabled = enabled)
            .onKeyEvent { e ->
                if (enabled && e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onClick(); true } else false
            }
            .padding(horizontal = 20.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        icon?.let { Icon(it, null, tint = Color.White, modifier = Modifier.size(16.dp)) }
        Text(text, color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.Medium)
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun ChipRowSelectable(
    options: List<String>,
    selectedIndex: Int,
    onSelect: (Int) -> Unit,
) {
    androidx.compose.foundation.layout.FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        options.forEachIndexed { idx, label ->
            Chip(
                label = label,
                selected = idx == selectedIndex,
                onClick = { onSelect(idx) },
            )
        }
    }
}

@Composable
private fun Chip(label: String, selected: Boolean, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val bg = when {
        selected -> Accent
        focused -> SurfaceHi
        else -> BgDark
    }
    val fg = if (selected) Color.White else OnSurface
    Row(
        Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(bg)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onClick(); true } else false
            }
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Text(label, color = fg, fontSize = 13.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun ToggleRow(
    label: String,
    hint: String? = null,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(if (focused) SurfaceHi else BgDark)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .onKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown &&
                    (e.key == Key.DirectionCenter || e.key == Key.Enter)
                ) { onCheckedChange(!checked); true } else false
            }
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, color = OnSurface, fontSize = 14.sp)
            hint?.let { Text(it, color = Muted, fontSize = 12.sp) }
        }
        Checkbox(
            checked = checked,
            onCheckedChange = null,   // Row handelt es
            colors = CheckboxDefaults.colors(checkedColor = Accent),
        )
    }
}

