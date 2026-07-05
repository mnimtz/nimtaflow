package email.nimtz.nimtaflow.tv.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.api.Album
import email.nimtz.nimtaflow.tv.api.Person
import email.nimtz.nimtaflow.tv.screensaver.ScreensaverPrefs
import email.nimtz.nimtaflow.tv.ui.theme.*
import email.nimtz.nimtaflow.tv.util.ReleaseInfo
import email.nimtz.nimtaflow.tv.util.UpdateChecker
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*

@Composable
fun FireTVSettingsScreen(api: APIClient) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val prefs = (context.applicationContext as email.nimtz.nimtaflow.tv.NimtaFlowApp).prefs

    // App-Version aus PackageInfo
    val versionName = remember {
        try { context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "?" }
        catch (_: Exception) { "?" }
    }

    // Server-APK Status
    var apkAvailable by remember { mutableStateOf<Boolean?>(null) }
    var apkSizeMb    by remember { mutableStateOf(0.0) }
    var publicUrl    by remember { mutableStateOf("") }

    // Auto-Update
    var autoUpdate by remember { mutableStateOf(false) }

    // Update prüfen
    var checkResult  by remember { mutableStateOf<String?>(null) }
    var checking     by remember { mutableStateOf(false) }
    var latestRelease by remember { mutableStateOf<ReleaseInfo?>(null) }

    // In-App Update Download
    var updateProgress by remember { mutableStateOf(-1) }
    val lastInstalled  by prefs.lastInstalledRelease.collectAsState(initial = "")

    // ADB Geräte
    var adbDevices   by remember { mutableStateOf<List<AdbDevice>>(emptyList()) }
    var scanning     by remember { mutableStateOf(false) }
    var installing   by remember { mutableStateOf<String?>(null) }
    var installMsg   by remember { mutableStateOf<String?>(null) }

    data class AdbDevice(val id: String, val model: String, val state: String)

    // Beim Start: Server-APK-Status + Settings laden
    LaunchedEffect(Unit) {
        try {
            val info = api.getJson("api/v1/software/firetv")
            apkAvailable = info["available"]?.jsonPrimitive?.boolean ?: false
            apkSizeMb    = info["size_mb"]?.jsonPrimitive?.double ?: 0.0
        } catch (_: Exception) {}
        try {
            val s = api.getJson("api/settings")
            autoUpdate = s["firetv.auto_update"]?.jsonPrimitive?.content == "true"
            publicUrl  = s["firetv.public_url"]?.jsonPrimitive?.content ?: ""
        } catch (_: Exception) {}
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BgDark)
            .verticalScroll(rememberScrollState())
            .padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        Text("Einstellungen", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = OnSurface)

        // ── App-Version ──────────────────────────────────────────────────────
        SettingsCard("Diese App") {
            SettingsRow(label = "Version", value = "NimtaFlow TV  $versionName")
        }

        // ── Server-APK Status ────────────────────────────────────────────────
        SettingsCard("Server-APK") {
            when (apkAvailable) {
                true  -> SettingsRow(
                    icon = { Icon(Icons.Filled.CheckCircle, null, tint = Color(0xFF4CAF50), modifier = Modifier.size(18.dp)) },
                    label = "APK bereit",
                    value = if (apkSizeMb > 0) String.format("%.1f MB", apkSizeMb) else "",
                )
                false -> SettingsRow(
                    icon = { Icon(Icons.Filled.Error, null, tint = Muted, modifier = Modifier.size(18.dp)) },
                    label = "Kein APK vorhanden",
                    value = "",
                )
                null -> LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = Accent)
            }
            if (publicUrl.isNotEmpty()) {
                SettingsRow(label = "Öffentliche URL", value = publicUrl)
            }
        }

        // ── Auto-Update ──────────────────────────────────────────────────────
        SettingsCard("Updates") {
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("Auto-Update (täglich)", color = OnSurface, fontSize = 15.sp)
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

            Spacer(Modifier.height(8.dp))

            // Update prüfen (auf GitHub)
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(
                    onClick = {
                        scope.launch {
                            checking = true; checkResult = null
                            try {
                                val release = UpdateChecker.fetchLatestRelease()
                                if (release != null) {
                                    latestRelease = release
                                    val newer = UpdateChecker.isNewer(release.publishedAt, lastInstalled)
                                    checkResult = if (newer) "Update verfügbar: ${release.releaseName}" else "App ist aktuell"
                                } else {
                                    checkResult = "Kein Release gefunden"
                                }
                            } catch (_: Exception) { checkResult = "Fehler beim Prüfen" }
                            finally { checking = false }
                        }
                    },
                    enabled = !checking && updateProgress < 0,
                    colors = ButtonDefaults.buttonColors(containerColor = Surface),
                ) {
                    if (checking) ProgressView()
                    else Icon(Icons.Filled.Refresh, null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Jetzt prüfen")
                }

                // Update installieren (wenn verfügbar)
                latestRelease?.let { release ->
                    if (UpdateChecker.isNewer(release.publishedAt, lastInstalled)) {
                        Button(
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
                                    } catch (_: Exception) {
                                    } finally {
                                        updateProgress = -1
                                    }
                                }
                            },
                            enabled = updateProgress < 0,
                            colors = ButtonDefaults.buttonColors(containerColor = Accent),
                        ) {
                            Icon(Icons.Filled.Download, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Installieren")
                        }
                    }
                }
            }

            if (updateProgress in 0..100) {
                Spacer(Modifier.height(8.dp))
                LinearProgressIndicator(
                    progress = { updateProgress / 100f },
                    modifier = Modifier.fillMaxWidth(),
                    color = Accent,
                )
                Text("Herunterladen… $updateProgress %", color = Muted, fontSize = 12.sp)
            }

            checkResult?.let { Text(it, color = Muted, fontSize = 13.sp) }
        }

        // ── ADB Autodiscover ─────────────────────────────────────────────────
        SettingsCard("FireTV auf anderen Geräten installieren") {
            Text(
                "Scannt das WLAN nach Android-Geräten mit aktiviertem ADB (Port 5555). " +
                "Developer-Modus + Netzwerk-ADB muss am Zielgerät aktiviert sein.",
                color = Muted, fontSize = 13.sp,
            )
            Spacer(Modifier.height(8.dp))

            Button(
                onClick = {
                    scope.launch {
                        scanning = true; adbDevices = emptyList(); installMsg = null
                        try {
                            val result = api.getJson("api/v1/software/firetv/adb-devices")
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
                enabled = !scanning,
                colors = ButtonDefaults.buttonColors(containerColor = Surface),
            ) {
                if (scanning) ProgressView()
                else Icon(Icons.Filled.Wifi, null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Geräte suchen")
            }

            adbDevices.forEach { device ->
                Spacer(Modifier.height(8.dp))
                Row(
                    Modifier
                        .fillMaxWidth()
                        .background(BgDark, RoundedCornerShape(8.dp))
                        .padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column {
                        Text(device.model, color = OnSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                        Text(device.id, color = Muted, fontSize = 12.sp)
                    }
                    Button(
                        onClick = {
                            scope.launch {
                                installing = device.id
                                try {
                                    api.postJson(
                                        "api/v1/software/firetv/adb-install",
                                        buildJsonObject { put("device_id", device.id) }
                                    )
                                    installMsg = "Installation auf ${device.model} gestartet — bitte am Gerät bestätigen"
                                } catch (_: Exception) {
                                    installMsg = "Installation fehlgeschlagen"
                                } finally {
                                    installing = null
                                }
                            }
                        },
                        enabled = installing == null,
                        colors = ButtonDefaults.buttonColors(containerColor = Accent),
                    ) {
                        if (installing == device.id) ProgressView()
                        else Text("Installieren")
                    }
                }
            }

            installMsg?.let { Spacer(Modifier.height(4.dp)); Text(it, color = Muted, fontSize = 13.sp) }
        }

        // ── Bildschirmschoner ────────────────────────────────────────────────
        ScreensaverSettingsCard(api)
    }
}

@Composable
private fun ScreensaverSettingsCard(api: APIClient) {
    val context = LocalContext.current
    val scope   = rememberCoroutineScope()
    val ssPrefs = remember { ScreensaverPrefs(context) }

    val mode        by ssPrefs.mode.collectAsState(initial = "all")
    val personRaw   by ssPrefs.personIds.collectAsState(initial = "")
    val albumRaw    by ssPrefs.albumIds.collectAsState(initial = "")
    val intervalSec by ssPrefs.intervalSec.collectAsState(initial = 10)
    val showInfo    by ssPrefs.showInfo.collectAsState(initial = false)

    var persons by remember { mutableStateOf<List<Person>>(emptyList()) }
    var albums  by remember { mutableStateOf<List<Album>>(emptyList()) }

    // Personen + Alben einmalig laden (für Auswahl)
    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            runCatching { persons = api.persons() }
            runCatching { albums  = api.albums() }
        }
    }

    val selectedPersons = ssPrefs.personIdSet(personRaw)
    val selectedAlbums  = ssPrefs.albumIdSet(albumRaw)

    val MODES = listOf(
        "all"        to "Alle Fotos",
        "highlights" to "Highlights",
        "persons"    to "Personen",
        "albums"     to "Alben",
    )
    val INTERVALS = listOf(5 to "5 s", 10 to "10 s", 30 to "30 s", 60 to "1 min")

    SettingsCard("Bildschirmschoner") {
        Text(
            "Wird aktiv wenn FireTV den Bildschirmschoner startet " +
            "(Einstellungen → Anzeige & Ton → Bildschirmschoner).",
            color = Muted, fontSize = 13.sp,
        )
        Spacer(Modifier.height(4.dp))

        // Modus
        Text("Quelle", color = OnSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MODES.forEach { (key, label) ->
                val selected = mode == key
                Button(
                    onClick = { scope.launch { ssPrefs.saveMode(key) } },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (selected) Accent else Surface,
                    ),
                ) { Text(label, fontSize = 13.sp) }
            }
        }

        // Personen-Auswahl
        if (mode == "persons" && persons.isNotEmpty()) {
            Spacer(Modifier.height(4.dp))
            Text("Personen auswählen", color = OnSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            persons.forEach { person ->
                val checked = person.id in selectedPersons
                Row(
                    Modifier
                        .fillMaxWidth()
                        .background(BgDark, RoundedCornerShape(6.dp))
                        .padding(horizontal = 12.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(person.name, color = OnSurface, fontSize = 14.sp)
                    Checkbox(
                        checked = checked,
                        onCheckedChange = { on ->
                            val newSet = if (on) selectedPersons + person.id else selectedPersons - person.id
                            scope.launch { ssPrefs.savePersonIds(newSet.joinToString(",")) }
                        },
                        colors = CheckboxDefaults.colors(checkedColor = Accent),
                    )
                }
            }
        }

        // Alben-Auswahl
        if (mode == "albums" && albums.isNotEmpty()) {
            Spacer(Modifier.height(4.dp))
            Text("Alben auswählen", color = OnSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            albums.forEach { album ->
                val checked = album.id in selectedAlbums
                Row(
                    Modifier
                        .fillMaxWidth()
                        .background(BgDark, RoundedCornerShape(6.dp))
                        .padding(horizontal = 12.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column {
                        Text(album.name, color = OnSurface, fontSize = 14.sp)
                        Text("${album.photoCount} Fotos", color = Muted, fontSize = 12.sp)
                    }
                    Checkbox(
                        checked = checked,
                        onCheckedChange = { on ->
                            val newSet = if (on) selectedAlbums + album.id else selectedAlbums - album.id
                            scope.launch { ssPrefs.saveAlbumIds(newSet.joinToString(",")) }
                        },
                        colors = CheckboxDefaults.colors(checkedColor = Accent),
                    )
                }
            }
        }

        // Intervall
        Spacer(Modifier.height(4.dp))
        Text("Intervall", color = OnSurface, fontSize = 14.sp, fontWeight = FontWeight.Medium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            INTERVALS.forEach { (sec, label) ->
                val selected = intervalSec == sec
                Button(
                    onClick = { scope.launch { ssPrefs.saveIntervalSec(sec) } },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (selected) Accent else Surface,
                    ),
                ) { Text(label, fontSize = 13.sp) }
            }
        }

        // Info anzeigen
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

@Composable
private fun ProgressView() = CircularProgressIndicator(
    modifier = Modifier.size(16.dp),
    strokeWidth = 2.dp,
    color = Accent,
)

@Composable
private fun SettingsCard(title: String, content: @Composable ColumnScope.() -> Unit) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = Surface,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, color = Accent, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

@Composable
private fun SettingsRow(
    icon: (@Composable () -> Unit)? = null,
    label: String,
    value: String,
) {
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        icon?.invoke()
        Text(label, color = OnSurface, fontSize = 14.sp, modifier = Modifier.weight(1f))
        if (value.isNotEmpty()) Text(value, color = Muted, fontSize = 13.sp)
    }
}
