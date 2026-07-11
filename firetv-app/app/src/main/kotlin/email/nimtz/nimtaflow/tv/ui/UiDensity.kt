package email.nimtz.nimtaflow.tv.ui

import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * Zentrale Grid-Dichte für alle FireTV-Screens (Personen, Erinnerungen,
 * Dashboard-Kacheln). Der User schaltet zwischen 3 Stufen — "kompakt" für
 * einen 4K-TV auf dem Schreibtisch (mehr Inhalt pro Screen), "komfortabel"
 * für einen 720p-TV in 3 m Abstand (große Kacheln, gut lesbar aus der Ferne).
 */
enum class GridDensity(
    val id: String,
    val label: String,
    val hint: String,
    // Personen-Grid
    val personCellMin: Dp,     // GridCells.Adaptive Minimum
    val personAvatar: Dp,      // Avatar-Kreis
    val personCardPad: Dp,     // Padding um die Card
    // Erinnerungen (Fotostreifen)
    val memoryTile: Dp,        // quadratische Foto-Kachel
    // Dashboard: Rail-Kacheln
    val dashPhotoW: Dp, val dashPhotoH: Dp,
    val dashMemoryW: Dp, val dashMemoryH: Dp,
    val dashPersonAvatar: Dp,
    val dashAlbumW: Dp,
    // Gallery (Fotos-Grid)
    val galleryCellMin: Dp,
) {
    Compact(
        "compact", "Kompakt", "Mehr Inhalt pro Screen — ideal für 4K-Nähe",
        personCellMin = 140.dp, personAvatar = 78.dp, personCardPad = 10.dp,
        memoryTile = 150.dp,
        dashPhotoW = 160.dp, dashPhotoH = 105.dp,
        dashMemoryW = 190.dp, dashMemoryH = 118.dp,
        dashPersonAvatar = 76.dp,
        dashAlbumW = 170.dp,
        galleryCellMin = 180.dp,
    ),
    Medium(
        "medium", "Mittel", "Balance zwischen Übersicht und Größe",
        personCellMin = 180.dp, personAvatar = 110.dp, personCardPad = 14.dp,
        memoryTile = 200.dp,
        dashPhotoW = 200.dp, dashPhotoH = 130.dp,
        dashMemoryW = 240.dp, dashMemoryH = 150.dp,
        dashPersonAvatar = 100.dp,
        dashAlbumW = 220.dp,
        galleryCellMin = 240.dp,
    ),
    Comfy(
        "comfy", "Groß", "Große Kacheln — gut lesbar aus der Ferne",
        personCellMin = 240.dp, personAvatar = 150.dp, personCardPad = 20.dp,
        memoryTile = 260.dp,
        dashPhotoW = 260.dp, dashPhotoH = 170.dp,
        dashMemoryW = 300.dp, dashMemoryH = 190.dp,
        dashPersonAvatar = 130.dp,
        dashAlbumW = 280.dp,
        galleryCellMin = 300.dp,
    );

    companion object {
        fun fromId(id: String?): GridDensity =
            entries.firstOrNull { it.id == id } ?: Medium
    }
}

/**
 * CompositionLocal: jede Screen greift auf die aktuell konfigurierte Dichte zu,
 * ohne dass wir die Prefs-Instanz durch die halbe App reichen müssen.
 */
val LocalGridDensity = compositionLocalOf { GridDensity.Medium }

enum class PeopleSort(val id: String, val label: String) {
    ByPhotoCount("count", "Nach Fotoanzahl (viele zuerst)"),
    ByName("name", "Alphabetisch");

    companion object {
        fun fromId(id: String?): PeopleSort =
            entries.firstOrNull { it.id == id } ?: ByPhotoCount
    }
}

val LocalPeopleSort = compositionLocalOf { PeopleSort.ByPhotoCount }
