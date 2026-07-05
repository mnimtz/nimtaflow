package email.nimtz.nimtaflow.tv.api

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.logging.HttpLoggingInterceptor
import java.util.concurrent.TimeUnit

private val json = Json { ignoreUnknownKeys = true; isLenient = true }
private val jsonMedia = "application/json".toMediaType()

/** Wird geworfen wenn der Server 401 zurückgibt — löst in der UI einen Re-Login aus. */
class UnauthorizedException : Exception("Token abgelaufen oder ungültig")

class APIClient(private var baseUrl: String, private var token: String = "") {

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        })
        .build()

    fun setBaseUrl(url: String) { baseUrl = url.trimEnd('/') }
    fun setToken(t: String) { token = t }
    fun hasToken() = token.isNotBlank()

    fun thumbUrl(photoId: Int, size: String = "medium") =
        "$baseUrl/api/photos/$photoId/thumbnail?size=$size"

    fun streamUrl(photoId: Int) =
        "$baseUrl/api/v1/photos/$photoId/stream?access_token=$token"

    private fun get(path: String): String {
        val req = Request.Builder()
            .url("$baseUrl$path")
            .apply { if (token.isNotBlank()) header("Authorization", "Bearer $token") }
            .build()
        return http.newCall(req).execute().use { resp ->
            if (resp.code == 401) throw UnauthorizedException()
            resp.body?.string() ?: ""
        }
    }

    private fun post(path: String, body: String): String {
        val req = Request.Builder()
            .url("$baseUrl$path")
            .apply { if (token.isNotBlank()) header("Authorization", "Bearer $token") }
            .post(body.toRequestBody(jsonMedia))
            .build()
        return http.newCall(req).execute().use { resp ->
            if (resp.code == 401) throw UnauthorizedException()
            resp.body?.string() ?: ""
        }
    }

    // ── Photos ───────────────────────────────────────────────────────────────

    fun photos(
        page: Int = 1,
        limit: Int = 60,
        view: String = "library",
        personId: Int? = null,
        sort: String = "newest",
    ): PhotoListResponse {
        var url = "/api/photos?page=$page&limit=$limit&view=$view&sort=$sort"
        if (personId != null) url += "&person_id=$personId"
        return json.decodeFromString(get(url))
    }

    fun favorites(page: Int = 1, limit: Int = 60): PhotoListResponse =
        json.decodeFromString(get("/api/photos?page=$page&limit=$limit&view=favorites&sort=newest"))

    fun toggleFavorite(photoId: Int, isFavorite: Boolean) {
        val body = """{"is_favorite":$isFavorite}"""
        try {
            val req = Request.Builder()
                .url("$baseUrl/api/photos/$photoId/meta")
                .apply { if (token.isNotBlank()) header("Authorization", "Bearer $token") }
                .method("PATCH", body.toRequestBody(jsonMedia))
                .build()
            http.newCall(req).execute().use { /* ignore body */ }
        } catch (_: Exception) { /* best-effort */ }
    }

    // ── Albums ────────────────────────────────────────────────────────────────

    fun albums(): List<Album> =
        json.decodeFromString(get("/api/albums"))

    fun albumPhotos(albumId: Int, page: Int = 1, limit: Int = 200): PhotoListResponse =
        json.decodeFromString(get("/api/albums/$albumId/photos?page=$page&limit=$limit"))

    // ── Persons ───────────────────────────────────────────────────────────────

    fun persons(): List<Person> =
        runCatching { json.decodeFromString<List<Person>>(get("/api/persons")) }.getOrDefault(emptyList())

    // ── Auth/Me ───────────────────────────────────────────────────────────────

    fun me(): UserMe? =
        runCatching { json.decodeFromString<UserMe>(get("/api/auth/me")) }.getOrNull()

    // ── Memories ──────────────────────────────────────────────────────────────

    fun memories(): List<MemoryGroup> =
        json.decodeFromString(get("/api/photos/memories"))

    // ── Device Auth ───────────────────────────────────────────────────────────

    fun requestDeviceCode(): DeviceCodeResponse =
        json.decodeFromString(post("/api/device/code", "{}"))

    fun pollDeviceToken(deviceCode: String): DeviceTokenResponse =
        json.decodeFromString(get("/api/device/token?device_code=$deviceCode"))

    // ── Generic JSON helpers (suspend, für Settings-Screen) ───────────────────

    suspend fun getJson(path: String): JsonObject = withContext(Dispatchers.IO) {
        val raw = get(if (path.startsWith("/")) path else "/$path")
        json.parseToJsonElement(raw) as? JsonObject ?: JsonObject(emptyMap())
    }

    suspend fun postJson(path: String, body: JsonObject = buildJsonObject {}): JsonObject = withContext(Dispatchers.IO) {
        val raw = post(if (path.startsWith("/")) path else "/$path", body.toString())
        json.parseToJsonElement(raw) as? JsonObject ?: JsonObject(emptyMap())
    }

    suspend fun patchSettings(settings: Map<String, String>): Unit = withContext(Dispatchers.IO) {
        val bodyStr = buildJsonObject { settings.forEach { (k, v) -> put(k, v) } }.toString()
        val req = Request.Builder()
            .url("$baseUrl/api/settings")
            .apply { if (token.isNotBlank()) header("Authorization", "Bearer $token") }
            .method("PATCH", bodyStr.toRequestBody(jsonMedia))
            .build()
        http.newCall(req).execute().use { /* ignore body */ }
    }
}
