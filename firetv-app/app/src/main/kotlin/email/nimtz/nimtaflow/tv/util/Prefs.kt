package email.nimtz.nimtaflow.tv.util

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore("nimtaflow_tv")

private val KEY_TOKEN          = stringPreferencesKey("access_token")
private val KEY_REFRESH        = stringPreferencesKey("refresh_token")
private val KEY_URL            = stringPreferencesKey("server_url")
private val KEY_LAST_RELEASE   = stringPreferencesKey("last_installed_release")
private val KEY_IS_ADMIN       = booleanPreferencesKey("is_admin")
// UI-Konfiguration: Grid-Dichte + Sortierung pro Screen
private val KEY_GRID_DENSITY   = stringPreferencesKey("grid_density")   // "compact"|"medium"|"comfy"
private val KEY_PEOPLE_SORT    = stringPreferencesKey("people_sort")    // "count"|"name"

class Prefs(private val ctx: Context) {

    val serverUrl: Flow<String>            = ctx.dataStore.data.map { it[KEY_URL] ?: "" }
    val token: Flow<String>               = ctx.dataStore.data.map { it[KEY_TOKEN] ?: "" }
    val lastInstalledRelease: Flow<String> = ctx.dataStore.data.map { it[KEY_LAST_RELEASE] ?: "" }
    val isAdmin: Flow<Boolean>             = ctx.dataStore.data.map { it[KEY_IS_ADMIN] ?: false }
    val gridDensity: Flow<String>          = ctx.dataStore.data.map { it[KEY_GRID_DENSITY] ?: "medium" }
    val peopleSort: Flow<String>           = ctx.dataStore.data.map { it[KEY_PEOPLE_SORT] ?: "count" }

    suspend fun saveGridDensity(v: String) {
        ctx.dataStore.edit { it[KEY_GRID_DENSITY] = v }
    }

    suspend fun savePeopleSort(v: String) {
        ctx.dataStore.edit { it[KEY_PEOPLE_SORT] = v }
    }

    suspend fun saveServerUrl(url: String) {
        ctx.dataStore.edit { it[KEY_URL] = url.trimEnd('/') }
    }

    suspend fun saveTokens(access: String, refresh: String) {
        ctx.dataStore.edit { it[KEY_TOKEN] = access; it[KEY_REFRESH] = refresh }
    }

    suspend fun saveIsAdmin(admin: Boolean) {
        ctx.dataStore.edit { it[KEY_IS_ADMIN] = admin }
    }

    suspend fun clearTokens() {
        ctx.dataStore.edit {
            it.remove(KEY_TOKEN); it.remove(KEY_REFRESH); it.remove(KEY_IS_ADMIN)
        }
    }

    suspend fun saveLastInstalledRelease(publishedAt: String) {
        ctx.dataStore.edit { it[KEY_LAST_RELEASE] = publishedAt }
    }
}
