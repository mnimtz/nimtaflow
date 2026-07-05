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
    val name: String,
    @SerialName("photo_count")     val photoCount: Int = 0,
    @SerialName("sample_photo_id") val samplePhotoId: Int? = null,
)

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
    val items: List<Photo>,
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
