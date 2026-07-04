package email.nimtz.nimtaflow.tv.util

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore("nimtaflow_tv")

private val KEY_TOKEN   = stringPreferencesKey("access_token")
private val KEY_REFRESH = stringPreferencesKey("refresh_token")
private val KEY_URL     = stringPreferencesKey("server_url")

class Prefs(private val ctx: Context) {

    val serverUrl: Flow<String> = ctx.dataStore.data.map { it[KEY_URL] ?: "" }
    val token: Flow<String>     = ctx.dataStore.data.map { it[KEY_TOKEN] ?: "" }

    suspend fun saveServerUrl(url: String) {
        ctx.dataStore.edit { it[KEY_URL] = url.trimEnd('/') }
    }

    suspend fun saveTokens(access: String, refresh: String) {
        ctx.dataStore.edit { it[KEY_TOKEN] = access; it[KEY_REFRESH] = refresh }
    }

    suspend fun clearTokens() {
        ctx.dataStore.edit { it.remove(KEY_TOKEN); it.remove(KEY_REFRESH) }
    }
}
