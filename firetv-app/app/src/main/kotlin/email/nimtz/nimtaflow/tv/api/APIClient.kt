package email.nimtz.nimtaflow.tv.api

import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.logging.HttpLoggingInterceptor
import java.util.concurrent.TimeUnit

private val json = Json { ignoreUnknownKeys = true; isLenient = true }
private val jsonMedia = "application/json".toMediaType()

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
        return http.newCall(req).execute().use { it.body!!.string() }
    }

    private fun post(path: String, body: String): String {
        val req = Request.Builder()
            .url("$baseUrl$path")
            .apply { if (token.isNotBlank()) header("Authorization", "Bearer $token") }
            .post(body.toRequestBody(jsonMedia))
            .build()
        return http.newCall(req).execute().use { it.body!!.string() }
    }

    // ── Photos ───────────────────────────────────────────────────────────────

    fun photos(page: Int = 1, limit: Int = 60, view: String = "library"): PhotoListResponse =
        json.decodeFromString(get("/api/photos?page=$page&limit=$limit&view=$view&sort=newest"))

    fun favorites(page: Int = 1, limit: Int = 60): PhotoListResponse =
        json.decodeFromString(get("/api/photos?page=$page&limit=$limit&view=favorites&sort=newest"))

    // ── Albums ────────────────────────────────────────────────────────────────

    fun albums(): List<Album> =
        json.decodeFromString(get("/api/albums"))

    fun albumPhotos(albumId: Int, page: Int = 1, limit: Int = 60): PhotoListResponse =
        json.decodeFromString(get("/api/albums/$albumId/photos?page=$page&limit=$limit"))

    // ── Memories ──────────────────────────────────────────────────────────────

    fun memories(): List<MemoryGroup> =
        json.decodeFromString(get("/api/photos/memories"))

    // ── Device Auth ───────────────────────────────────────────────────────────

    fun requestDeviceCode(): DeviceCodeResponse =
        json.decodeFromString(post("/api/device/code", "{}"))

    fun pollDeviceToken(deviceCode: String): DeviceTokenResponse =
        json.decodeFromString(get("/api/device/token?device_code=$deviceCode"))
}
