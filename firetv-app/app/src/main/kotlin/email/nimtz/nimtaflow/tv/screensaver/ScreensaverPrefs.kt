package email.nimtz.nimtaflow.tv.screensaver

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.ssDataStore: DataStore<Preferences> by preferencesDataStore("nimtaflow_tv_screensaver")

private val KEY_MODE     = stringPreferencesKey("mode")
private val KEY_PERSONS  = stringPreferencesKey("person_ids")   // comma-separated int IDs
private val KEY_ALBUMS   = stringPreferencesKey("album_ids")    // comma-separated int IDs
private val KEY_INTERVAL = intPreferencesKey("interval_sec")
private val KEY_INFO     = booleanPreferencesKey("show_info")

class ScreensaverPrefs(private val ctx: Context) {

    // "all" | "persons" | "albums" | "highlights"
    val mode:        Flow<String>  = ctx.ssDataStore.data.map { it[KEY_MODE]     ?: "all" }
    val personIds:   Flow<String>  = ctx.ssDataStore.data.map { it[KEY_PERSONS]  ?: "" }
    val albumIds:    Flow<String>  = ctx.ssDataStore.data.map { it[KEY_ALBUMS]   ?: "" }
    val intervalSec: Flow<Int>     = ctx.ssDataStore.data.map { it[KEY_INTERVAL] ?: 10 }
    val showInfo:    Flow<Boolean> = ctx.ssDataStore.data.map { it[KEY_INFO]     ?: false }

    suspend fun saveMode(m: String)         { ctx.ssDataStore.edit { it[KEY_MODE]     = m } }
    suspend fun savePersonIds(raw: String)  { ctx.ssDataStore.edit { it[KEY_PERSONS]  = raw } }
    suspend fun saveAlbumIds(raw: String)   { ctx.ssDataStore.edit { it[KEY_ALBUMS]   = raw } }
    suspend fun saveIntervalSec(s: Int)     { ctx.ssDataStore.edit { it[KEY_INTERVAL] = s } }
    suspend fun saveShowInfo(v: Boolean)    { ctx.ssDataStore.edit { it[KEY_INFO]     = v } }

    fun personIdSet(raw: String): Set<Int> =
        raw.split(",").mapNotNull { it.trim().toIntOrNull() }.toSet()

    fun albumIdSet(raw: String): Set<Int> =
        raw.split(",").mapNotNull { it.trim().toIntOrNull() }.toSet()
}
