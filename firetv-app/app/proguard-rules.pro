# Keep all API model + serialization classes
-keep class email.nimtz.nimtaflow.tv.api.** { *; }
-keepclassmembers class email.nimtz.nimtaflow.tv.api.** { *; }

# Kotlin Serialization — keep generated $serializer companions
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers @kotlinx.serialization.Serializable class ** {
    *** Companion;
    *** INSTANCE;
    kotlinx.serialization.KSerializer serializer(...);
}
-keepclassmembers class ** implements kotlinx.serialization.Serializable {
    private static final ** $serializer;
}
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class okhttp3.** { *; }
-keep class okio.** { *; }

# Coil
-dontwarn coil.**

# ZXing
-keep class com.google.zxing.** { *; }

# Media3 / ExoPlayer
-keep class androidx.media3.** { *; }
-dontwarn androidx.media3.**

# DataStore
-keep class androidx.datastore.** { *; }
-dontwarn androidx.datastore.**
