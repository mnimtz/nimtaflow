import Foundation

struct PhotoV1: Codable, Identifiable, Hashable {
    let id: Int
    let filename: String
    let taken_at: String?
    let width: Int?
    let height: Int?
    let latitude: Double?
    let longitude: Double?
    let is_video: Bool
    let duration_seconds: Double?
    var is_favorite: Bool
    let is_archived: Bool
    let is_trashed: Bool
    let status: String
    let thumb_url: String
    let thumb_medium_url: String
    let original_url: String
    let video_url: String?
    let location_name: String?
}

struct PhotoPage: Codable {
    let items: [PhotoV1]
    let next_cursor: Int?
    let total: Int
    let has_more: Bool
}

struct PersonV1: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let face_count: Int
    var photo_count: Int
    let avatar_url: String

    enum CodingKeys: String, CodingKey { case id, name, face_count, photo_count, avatar_url }
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        face_count = try c.decode(Int.self, forKey: .face_count)
        photo_count = (try? c.decode(Int.self, forKey: .photo_count)) ?? 0
        avatar_url = try c.decode(String.self, forKey: .avatar_url)
    }
}

struct AlbumV1: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let album_type: String
    let photo_count: Int
    let cover_url: String?

    enum CodingKeys: String, CodingKey { case id, name, album_type, photo_count, cover_url }
    init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        album_type = try c.decode(String.self, forKey: .album_type)
        photo_count = try c.decode(Int.self, forKey: .photo_count)
        cover_url = try? c.decodeIfPresent(String.self, forKey: .cover_url)
    }
}

struct DeviceCodeResponse: Codable {
    let device_code: String
    let user_code: String
    let qr_url: String
    let expires_in: Int
    let interval: Int
}

struct DevicePollResponse: Codable {
    let status: String
    let access_token: String?
    let refresh_token: String?
}
