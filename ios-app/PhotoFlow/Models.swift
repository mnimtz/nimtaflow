import Foundation

// MARK: - Photos (matches /api/v1 PhotoV1)

struct PhotoV1: Codable, Identifiable, Hashable {
    let id: Int
    let filename: String
    let taken_at: String?
    let width: Int?
    let height: Int?
    let aspect_ratio: Double?
    let latitude: Double?
    let longitude: Double?
    let is_video: Bool
    let duration_seconds: Double?
    var is_favorite: Bool
    let is_archived: Bool
    let is_trashed: Bool
    let user_rating: Int?
    let status: String
    let thumb_url: String
    let thumb_medium_url: String
    let original_url: String
    let video_url: String?
    let preview_url: String?
}

struct PhotoPage: Codable {
    let items: [PhotoV1]
    let next_cursor: Int?
    let total: Int
    let has_more: Bool
}

// MARK: - People

struct PersonV1: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let face_count: Int
    let avatar_url: String
}

// /api/people (management) — richer person record
struct Person: Codable, Identifiable, Hashable {
    let id: Int
    var name: String
    let alias: String?
    let birthdate: String?
    let face_count: Int
    let is_hidden: Bool?
}

struct FaceRef: Codable, Identifiable, Hashable {
    let id: Int
    let photo_id: Int
    let confidence: Double?
}

// MARK: - Relationships

struct RelGraph: Codable {
    let nodes: [RelNode]
    let edges: [RelEdge]
}
struct RelNode: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let face_count: Int
}
struct RelEdge: Codable, Identifiable, Hashable {
    let id: Int
    let from: Int
    let to: Int
    let type: String
    let category: String
    let directed: Bool
}

struct PersonRel: Codable, Identifiable, Hashable {
    let id: Int
    let other_id: Int
    let other_name: String
    let type: String
    let category: String
    let label: String
    let outgoing: Bool
}

struct TokenResponse: Codable {
    let access_token: String
    let refresh_token: String
}

// MARK: - Albums

struct AlbumV1: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let description: String?
    let album_type: String
    let photo_count: Int
    let cover_url: String?
}

// MARK: - Map

struct MapPointV1: Codable, Identifiable, Hashable {
    let id: Int
    let latitude: Double
    let longitude: Double
    let is_video: Bool
}

struct MapClusterV1: Codable, Hashable {
    let latitude: Double
    let longitude: Double
    let count: Int
    let photo_id: Int?
    let is_video: Bool
}

// MARK: - Trips / events

struct TripEventV1: Codable, Identifiable, Hashable {
    let count: Int
    let date_from: String
    let date_to: String
    let days: Int
    let city: String?
    let is_trip: Bool
    let cover_photo_id: Int?
    let cover_url: String?
    var id: String { "\(date_from)-\(date_to)" }
}

struct TripsV1: Codable {
    let home_city: String?
    let events: [TripEventV1]
}

struct TripWaypoint: Codable, Hashable {
    let place: String
    let country: String?
    let date: String?
    let lat: Double?
    let lng: Double?
    let note: String?
}

struct TripPlan: Codable {
    let name: String
    let date_from: String?
    let date_to: String?
    let summary: String?
    let waypoints: [TripWaypoint]
}

struct CreateTripResult: Codable {
    let album_id: Int
    let added: Int
    let name: String
}

// MARK: - Faces in a photo

struct PhotoFace: Codable, Identifiable {
    let face_id: Int
    let person_id: Int
    let person_name: String
    var id: Int { face_id }
}

// MARK: - Library stats

struct LibraryStats: Codable {
    let total: Int
    let images: Int
    let videos: Int
    let processing: Int
    let described: Int
    let with_faces: Int
    let favorites: Int
    let with_gps: Int
    let date_min: String?
    let date_max: String?
}

// MARK: - Photo detail (GET /api/v1/photos/{id}/detail)

struct PhotoPersonV1: Codable, Identifiable, Hashable {
    let person_id: Int
    let name: String
    var id: Int { person_id }
}

struct PhotoDetailV1: Codable {
    let id: Int
    let filename: String
    let taken_at: String?
    let width: Int?
    let height: Int?
    let is_video: Bool
    let latitude: Double?
    let longitude: Double?
    let description: String?
    let city: String?
    let country: String?
    let location_name: String?
    let camera_make: String?
    let camera_model: String?
    let lens_model: String?
    let focal_length: Double?
    let aperture: Double?
    let shutter_speed: String?
    let iso: Int?
    let file_size: Int?
    let tags: [String]
    let people: [PhotoPersonV1]
}

// MARK: - Scan progress (GET /api/sources/scan-progress)

struct ScanProgress: Codable {
    let total: Int        // media files found on disk across all sources
    let scanned: Int      // files walked so far
    let running: Bool
}

// MARK: - Memories

struct MemoryGroupV1: Codable, Identifiable {
    let years_ago: Int
    let date: String
    let items: [PhotoV1]
    var id: Int { years_ago }
}

// MARK: - Upload

struct UploadResult: Codable {
    let id: Int?
    let filename: String
    let status: String          // "accepted" | "duplicate" | "error..."
    let duplicate_of: Int?
}

// MARK: - Sharing

struct ShareOut: Codable, Identifiable, Hashable {
    let id: Int
    let token: String
    let url: String
    let share_type: String
    let title: String?
    let has_password: Bool
    let expires_at: String?
    let allow_download: Bool
    let view_count: Int
}

// MARK: - Chat

struct ChatStatus: Codable {
    let provider: String
    let gemini_ready: Bool
}

struct ChatTurn: Codable, Hashable {
    let role: String       // "user" | "assistant"
    let content: String
}

struct ChatReply: Codable {
    let answer: String
    let photo_ids: [Int]
}
