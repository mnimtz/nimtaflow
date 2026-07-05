package email.nimtz.nimtaflow.tv.util

import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.time.Instant

data class ReleaseInfo(
    val publishedAt: String,
    val downloadUrl: String,
    val releaseName: String,
)

object UpdateChecker {
    private const val RELEASE_API =
        "https://api.github.com/repos/mnimtz/nimtaflow/releases/tags/firetv-latest"

    suspend fun fetchLatestRelease(): ReleaseInfo? = withContext(Dispatchers.IO) {
        try {
            val client = OkHttpClient()
            val req = Request.Builder()
                .url(RELEASE_API)
                .header("Accept", "application/vnd.github+json")
                .build()
            val resp = client.newCall(req).execute()
            if (!resp.isSuccessful) return@withContext null
            val body = resp.body?.string() ?: return@withContext null
            val json = Json.parseToJsonElement(body).jsonObject
            val apkAsset = json["assets"]?.jsonArray
                ?.firstOrNull { it.jsonObject["name"]?.jsonPrimitive?.content?.endsWith(".apk") == true }
                ?: return@withContext null
            ReleaseInfo(
                publishedAt  = json["published_at"]?.jsonPrimitive?.content ?: return@withContext null,
                downloadUrl  = apkAsset.jsonObject["browser_download_url"]?.jsonPrimitive?.content ?: return@withContext null,
                releaseName  = json["name"]?.jsonPrimitive?.content ?: "Update",
            )
        } catch (_: Exception) { null }
    }

    fun isNewer(releasePublishedAt: String, lastInstalledAt: String): Boolean {
        if (lastInstalledAt.isEmpty()) return true
        return try {
            Instant.parse(releasePublishedAt) > Instant.parse(lastInstalledAt)
        } catch (_: Exception) { false }
    }

    suspend fun downloadAndInstall(
        context: Context,
        downloadUrl: String,
        onProgress: (Int) -> Unit,
    ) = withContext(Dispatchers.IO) {
        val client = OkHttpClient()
        val req = Request.Builder().url(downloadUrl).build()
        val resp = client.newCall(req).execute()
        if (!resp.isSuccessful) throw Exception("Download fehlgeschlagen: ${resp.code}")
        val responseBody = resp.body ?: throw Exception("Leere Antwort")
        val total = responseBody.contentLength()
        val apkFile = File(context.cacheDir, "nimtaflow-update.apk")

        responseBody.byteStream().use { input ->
            apkFile.outputStream().use { output ->
                val buffer = ByteArray(8 * 1024)
                var downloaded = 0L
                var read: Int
                while (input.read(buffer).also { read = it } != -1) {
                    output.write(buffer, 0, read)
                    downloaded += read
                    if (total > 0) onProgress((downloaded * 100 / total).toInt())
                }
            }
        }

        val uri = FileProvider.getUriForFile(
            context, "${context.packageName}.fileprovider", apkFile,
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }
}
