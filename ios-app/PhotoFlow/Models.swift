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
    let thumb_url: String
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
