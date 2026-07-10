package email.nimtz.nimtaflow.tv

import android.app.Application
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.disk.DiskCache
import coil.memory.MemoryCache
import coil.request.CachePolicy
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.util.Prefs
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

class NimtaFlowApp : Application(), ImageLoaderFactory {
    lateinit var api: APIClient
    lateinit var prefs: Prefs

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        api = APIClient("")
    }

    /**
     * Zentraler Coil-ImageLoader für die ganze App. Gründe:
     *  - Vorher: jeder AsyncImage baute einen frischen OkHttpClient → doppelter
     *    Connection-Pool, kein HTTP/2-Multiplexing.
     *  - Memory-Cache 25% des App-Heaps (FireTV: ~150 MB Heap → ~37 MB Cache).
     *  - Disk-Cache 256 MB unter der App-Cache-Directory.
     *  - Authorization-Interceptor: Bearer-Token pro Request, KEIN Teil des
     *    Cache-Keys → Token-Rotation invalidiert die Bilder nicht.
     */
    override fun newImageLoader(): ImageLoader {
        val ok = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .callTimeout(60, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val req = chain.request()
                val token = api.currentToken()
                if (token.isNotBlank() && req.header("Authorization") == null) {
                    chain.proceed(req.newBuilder()
                        .header("Authorization", "Bearer $token")
                        .build())
                } else chain.proceed(req)
            }
            .build()

        return ImageLoader.Builder(this)
            .okHttpClient(ok)
            .memoryCache {
                MemoryCache.Builder(this)
                    .maxSizePercent(0.25)   // ~1/4 des App-Heaps
                    .build()
            }
            .diskCache {
                DiskCache.Builder()
                    .directory(cacheDir.resolve("image_cache"))
                    .maxSizeBytes(256L * 1024 * 1024)
                    .build()
            }
            .respectCacheHeaders(true)
            .crossfade(120)          // sanftes Einblenden, TV-typisch
            .memoryCachePolicy(CachePolicy.ENABLED)
            .diskCachePolicy(CachePolicy.ENABLED)
            .build()
    }
}
