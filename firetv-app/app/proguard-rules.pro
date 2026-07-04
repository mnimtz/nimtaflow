# Keep serialization classes
-keep class email.nimtz.nimtaflow.tv.api.** { *; }
-keepclassmembers class * {
    @kotlinx.serialization.SerialName <fields>;
}

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**

# Coil
-dontwarn coil.**

# ZXing
-keep class com.google.zxing.** { *; }

# Media3 / ExoPlayer
-keep class androidx.media3.** { *; }
-dontwarn androidx.media3.**
