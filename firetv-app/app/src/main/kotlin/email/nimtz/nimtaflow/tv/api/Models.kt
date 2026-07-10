package email.nimtz.nimtaflow.tv.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class Photo(
    val id: Int,
    val filename: String = "",
    @SerialName("is_video")      val isVideo: Boolean = false,
    @SerialName("is_favorite")   val isFavorite: Boolean = false,
    @SerialName("taken_at")      val takenAt: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    @SerialName("location_name") val locationName: String? = null,
    val width: Int? = null,
    val height: Int? = null,
)

@Serializable
data class Person(
    val id: Int,
    val name: String = "",
    // Backend /api/people liefert `face_count` (nicht `photo_count`);
    // beide akzeptieren, damit ältere Server + Alias klappen.
    @SerialName("face_count")      val faceCount: Int = 0,
    @SerialName("photo_count")     val photoCount: Int = 0,
    // Backend liefert `profile_face_id` (nicht `sample_photo_id`) für den
    // Avatar-Endpoint /api/people/{id}/avatar. Wir bauen daraus die URL.
    @SerialName("profile_face_id") val profileFaceId: Int? = null,
    @SerialName("sample_photo_id") val samplePhotoId: Int? = null,
) {
    /** Gesamt-Anzahl Fotos für die Sortierung/Anzeige. */
    val effectivePhotoCount: Int get() = if (photoCount > 0) photoCount else faceCount
}

@Serializable
data class PhotoListResponse(
    val items: List<Photo>,
    val total: Int,
    val page: Int,
    val limit: Int,
)

@Serializable
data class Album(
    val id: Int,
    val name: String,
    @SerialName("photo_count") val photoCount: Int = 0,
    @SerialName("cover_photo_id") val coverPhotoId: Int? = null,
)

@Serializable
data class MemoryGroup(
    @SerialName("years_ago") val yearsAgo: Int,
    val date: String,
    // Backend liefert das Feld als "photos", nicht "items" → deshalb war die
    // Erinnerungs-Rail immer leer (Deserialisierung schlug pro Gruppe fehl).
    @SerialName("photos") val items: List<Photo> = emptyList(),
)

@Serializable
data class DeviceCodeResponse(
    @SerialName("device_code") val deviceCode: String,
    @SerialName("user_code") val userCode: String,
    @SerialName("qr_url") val qrUrl: String,
    @SerialName("expires_in") val expiresIn: Int,
    val interval: Int,
)

@Serializable
data class DeviceTokenResponse(
    val status: String,          // "pending" | "approved" | "expired"
    @SerialName("access_token") val accessToken: String? = null,
    @SerialName("refresh_token") val refreshToken: String? = null,
)

@Serializable
data class UserMe(
    val id: Int,
    val role: String,            // "admin" | "user"
    val name: String = "",
    val email: String = "",
    @SerialName("is_active") val isActive: Boolean = true,
)
