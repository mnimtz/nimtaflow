import Foundation

@MainActor
class APIClient: ObservableObject {
    @Published private(set) var serverURL: String = ""
    @Published private(set) var token: String = ""

    private let session = URLSession.shared

    func configure(serverURL: String, token: String) {
        self.serverURL = serverURL.trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        self.token = token
    }

    // Fixes URLs returned by the API: they may contain the wrong host/port
    // (nginx proxy strips :8090), so re-anchor them to our configured serverURL.
    func fixedURL(_ raw: String) -> URL? {
        if raw.hasPrefix("http"), let c = URLComponents(string: raw) {
            var pq = c.path
            if let q = c.query { pq += "?" + q }
            return URL(string: serverURL + pq)
        }
        let p = raw.hasPrefix("/") ? raw : "/" + raw
        return URL(string: serverURL + p)
    }

    func videoStreamURL(photoId: Int) -> URL? {
        URL(string: "\(serverURL)/api/v1/photos/\(photoId)/stream?access_token=\(token)")
    }

    // MARK: Requests

    func buildRequest(_ path: String, method: String = "GET", json: Any? = nil) -> URLRequest {
        makeRequest(path, method: method, json: json)
    }

    private func makeRequest(_ path: String, method: String = "GET", json: Any? = nil) -> URLRequest {
        let base = serverURL.isEmpty ? "http://localhost:8090" : serverURL
        let p = path.hasPrefix("/") ? path : "/" + path
        var req = URLRequest(url: URL(string: base + p)!)
        req.httpMethod = method
        req.timeoutInterval = 30
        if !token.isEmpty { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let json {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: json)
        }
        return req
    }

    func authHeaders() -> [String: String] {
        token.isEmpty ? [:] : ["Authorization": "Bearer \(token)"]
    }

    // MARK: Photos

    func fetchPhotos(cursor: Int? = nil, limit: Int = 60, favorites: Bool = false,
                     personId: Int? = nil, albumId: Int? = nil) async throws -> PhotoPage {
        var p = "api/v1/photos?limit=\(limit)"
        if let cursor { p += "&cursor=\(cursor)" }
        if favorites { p += "&favorites=true" }
        if let personId { p += "&person_id=\(personId)" }
        if let albumId { p += "&album_id=\(albumId)" }
        let (data, _) = try await session.data(for: makeRequest(p))
        return try JSONDecoder().decode(PhotoPage.self, from: data)
    }

    func fetchPersonPhotos(personId: Int, cursor: Int? = nil) async throws -> PhotoPage {
        var p = "api/v1/people/\(personId)/photos?limit=60"
        if let cursor { p += "&cursor=\(cursor)" }
        let (data, _) = try await session.data(for: makeRequest(p))
        return try JSONDecoder().decode(PhotoPage.self, from: data)
    }

    func fetchAlbumPhotos(albumId: Int, cursor: Int? = nil) async throws -> PhotoPage {
        var p = "api/v1/albums/\(albumId)/photos?limit=60"
        if let cursor { p += "&cursor=\(cursor)" }
        let (data, _) = try await session.data(for: makeRequest(p))
        return try JSONDecoder().decode(PhotoPage.self, from: data)
    }

    func fetchAllPhotos(limit: Int = 300) async -> [PhotoV1] {
        var all: [PhotoV1] = []
        var cursor: Int? = nil
        repeat {
            guard let page = try? await fetchPhotos(cursor: cursor, limit: 60) else { break }
            all += page.items
            cursor = page.next_cursor
            if all.count >= limit { break }
        } while cursor != nil
        return all
    }

    // MARK: Albums & People

    func fetchAlbums() async throws -> [AlbumV1] {
        let (data, _) = try await session.data(for: makeRequest("api/v1/albums"))
        return try JSONDecoder().decode([AlbumV1].self, from: data)
    }

    func fetchPeople() async throws -> [PersonV1] {
        let (data, _) = try await session.data(for: makeRequest("api/v1/people"))
        let all = try JSONDecoder().decode([PersonV1].self, from: data)
        return all.filter { $0.photo_count > 0 }.sorted { $0.photo_count > $1.photo_count }
    }

    // MARK: Actions

    func toggleFavorite(photoId: Int) async {
        _ = try? await session.data(for: makeRequest("api/v1/photos/\(photoId)/favorite", method: "PATCH"))
    }

    // MARK: Device Auth

    func requestDeviceCode() async throws -> DeviceCodeResponse {
        let req = makeRequest("api/device/code", method: "POST")
        let (data, _) = try await session.data(for: req)
        return try JSONDecoder().decode(DeviceCodeResponse.self, from: data)
    }

    func pollDeviceToken(deviceCode: String) async throws -> DevicePollResponse {
        let req = makeRequest("api/device/token?device_code=\(deviceCode)")
        let (data, _) = try await session.data(for: req)
        return try JSONDecoder().decode(DevicePollResponse.self, from: data)
    }
}
