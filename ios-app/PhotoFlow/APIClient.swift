import Foundation
import SwiftUI

/// Talks to the PhotoFlow server. Uses the iOS `/api/v1` feed endpoints plus the
/// regular `/api` endpoints for management actions (rename, merge, relationships).
@MainActor
final class APIClient: ObservableObject {
    static let shared = APIClient()

    @AppStorage("server_url") var serverURL: String = "http://your-server:8090"
    @AppStorage("access_token") var token: String = ""
    @AppStorage("refresh_token") var refresh: String = ""
    @Published var loggedIn: Bool = false

    init() { loggedIn = !token.isEmpty }

    private var base: URL { URL(string: serverURL.trimmingCharacters(in: .whitespaces))! }

    enum APIError: Error { case status(Int), badURL, decode }

    /// Build an absolute URL from a relative API path. Uses plain string joining
    /// (NOT URL.appendingPathComponent, which percent-encodes "?" and "&" and so
    /// mangles query strings → 404 on every request with parameters).
    func absoluteURL(_ path: String) -> URL {
        if path.hasPrefix("http") { return URL(string: path) ?? base }
        let b = serverURL.trimmingCharacters(in: .whitespaces)
        let base = b.hasSuffix("/") ? String(b.dropLast()) : b
        let p = path.hasPrefix("/") ? path : "/" + path
        return URL(string: base + p) ?? URL(string: base)!
    }

    private func makeRequest(_ path: String, method: String = "GET", json: Any? = nil) -> URLRequest {
        var req = URLRequest(url: absoluteURL(path))
        req.httpMethod = method
        if !token.isEmpty { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let json {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: json)
        }
        return req
    }

    func get<T: Decodable>(_ path: String, as type: T.Type) async throws -> T {
        try await send(makeRequest(path), as: type)
    }

    @discardableResult
    func send<T: Decodable>(_ request: URLRequest, as type: T.Type) async throws -> T {
        let (data, resp) = try await URLSession.shared.data(for: request)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { await logout(); throw APIError.status(401) }
        guard (200..<300).contains(code) else { throw APIError.status(code) }
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw APIError.decode }
    }

    @discardableResult
    func action(_ path: String, method: String, json: Any? = nil) async throws -> Bool {
        let (_, resp) = try await URLSession.shared.data(for: makeRequest(path, method: method, json: json))
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { await logout(); throw APIError.status(401) }
        guard (200..<300).contains(code) else { throw APIError.status(code) }
        return true
    }

    // Build a media URL. The server constructs absolute URLs from the request host,
    // but behind the nginx proxy that host loses the :8090 port (e.g.
    // "http://your-server/api/photos/…") → unreachable from the device. So we
    // ALWAYS re-anchor to our own serverURL: take only the path+query and prepend
    // the configured server. Fixes grey thumbnails/avatars across the whole app.
    func url(_ s: String) -> URL? {
        if s.hasPrefix("http"), let c = URLComponents(string: s) {
            var pq = c.path
            if let q = c.query { pq += "?" + q }
            return absoluteURL(pq)
        }
        return absoluteURL(s)
    }

    // MARK: Auth
    func login(username: String, password: String) async throws {
        var req = URLRequest(url: base.appendingPathComponent("api/auth/login"))
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        let body = "username=\(username.addingPercentEncoding(withAllowedCharacters: .urlQueryValueAllowed) ?? "")&password=\(password.addingPercentEncoding(withAllowedCharacters: .urlQueryValueAllowed) ?? "")"
        req.httpBody = body.data(using: .utf8)
        let tok = try await send(req, as: TokenResponse.self)
        token = tok.access_token; refresh = tok.refresh_token; loggedIn = true
    }

    func logout() async { token = ""; refresh = ""; loggedIn = false }

    // MARK: Feeds
    func photos(cursor: Int?, favorites: Bool = false, mediaType: String? = nil,
                sort: String = "newest", personId: Int? = nil) async throws -> PhotoPage {
        var p = "api/v1/photos?limit=60&sort=\(sort)"
        if let cursor { p += "&cursor=\(cursor)" }
        if favorites { p += "&favorites=true" }
        if let mediaType { p += "&media_type=\(mediaType)" }
        if let personId { p += "&person_id=\(personId)" }
        return try await get(p, as: PhotoPage.self)
    }
    func search(_ q: String) async throws -> PhotoPage {
        let enc = q.addingPercentEncoding(withAllowedCharacters: .urlQueryValueAllowed) ?? ""
        return try await get("api/v1/search?limit=80&q=\(enc)", as: PhotoPage.self)
    }
    func people() async throws -> [PersonV1] { try await get("api/v1/people", as: [PersonV1].self) }
    func personPhotos(_ id: Int, cursor: Int?) async throws -> PhotoPage {
        var p = "api/v1/people/\(id)/photos?limit=60"; if let cursor { p += "&cursor=\(cursor)" }
        return try await get(p, as: PhotoPage.self)
    }
    func relationshipsGraph() async throws -> RelGraph { try await get("api/v1/relationships", as: RelGraph.self) }
    func personRelationships(_ id: Int) async throws -> [PersonRel] { try await get("api/relationships/person/\(id)", as: [PersonRel].self) }
    func mapPhotos() async throws -> PhotoPage {
        // reuse the v1 feed then filter client-side for GPS (small libraries) — or the web list
        try await get("api/v1/photos?limit=200", as: PhotoPage.self)
    }

    // MARK: Mutations
    func toggleFavorite(_ id: Int) async throws { try await action("api/v1/photos/\(id)/favorite", method: "PATCH") }
    func renamePerson(_ id: Int, name: String) async throws { try await action("api/people/\(id)", method: "PATCH", json: ["name": name]) }
    func mergePeople(target: Int, sources: [Int]) async throws {
        try await action("api/people/merge-multi", method: "POST", json: ["target_id": target, "source_ids": sources])
    }
    func hidePerson(_ id: Int, hidden: Bool) async throws { try await action("api/people/\(id)/hide?hidden=\(hidden)", method: "POST") }
    func addRelationship(from: Int, to: Int, type: String) async throws {
        try await action("api/relationships", method: "POST", json: ["from_person_id": from, "to_person_id": to, "rel_type": type])
    }
    func deleteRelationship(_ id: Int) async throws { try await action("api/relationships/\(id)", method: "DELETE") }

    // MARK: Single photo
    func photo(_ id: Int) async throws -> PhotoV1 { try await get("api/v1/photos/\(id)", as: PhotoV1.self) }
    func setRating(_ id: Int, rating: Int) async throws { try await action("api/v1/photos/\(id)/rating?rating=\(rating)", method: "PATCH") }
    func reprocess(_ id: Int) async throws { try await action("api/photos/\(id)/reprocess", method: "POST") }

    // MARK: Albums
    func albums() async throws -> [AlbumV1] { try await get("api/v1/albums", as: [AlbumV1].self) }
    func albumPhotos(_ id: Int, cursor: Int?) async throws -> PhotoPage {
        var p = "api/v1/albums/\(id)/photos?limit=60"; if let cursor { p += "&cursor=\(cursor)" }
        return try await get(p, as: PhotoPage.self)
    }

    func photosByDate(from: String, to: String, cursor: Int?) async throws -> PhotoPage {
        var p = "api/v1/photos?limit=60&date_from=\(from)&date_to=\(to)"
        if let cursor { p += "&cursor=\(cursor)" }
        return try await get(p, as: PhotoPage.self)
    }

    // MARK: Trips / events
    func trips(tripsOnly: Bool = false, minPhotos: Int? = nil) async throws -> TripsV1 {
        var p = "api/v1/trips?trips_only=\(tripsOnly)"
        if let minPhotos { p += "&min_photos=\(minPhotos)" }
        return try await get(p, as: TripsV1.self)
    }

    // MARK: Map
    func mapPoints() async throws -> [MapPointV1] { try await get("api/v1/map", as: [MapPointV1].self) }

    // MARK: Upload
    func uploadFile(data: Data, filename: String, mime: String) async throws -> UploadResult {
        let boundary = "Boundary-\(UUID().uuidString)"
        var req = URLRequest(url: base.appendingPathComponent("api/v1/upload"))
        req.httpMethod = "POST"
        if !token.isEmpty { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        func add(_ s: String) { body.append(s.data(using: .utf8)!) }
        add("--\(boundary)\r\n")
        add("Content-Disposition: form-data; name=\"files\"; filename=\"\(filename)\"\r\n")
        add("Content-Type: \(mime)\r\n\r\n")
        body.append(data)
        add("\r\n--\(boundary)--\r\n")
        let (respData, resp) = try await URLSession.shared.upload(for: req, from: body)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 { await logout(); throw APIError.status(401) }
        guard (200..<300).contains(code) else { throw APIError.status(code) }
        let results = try JSONDecoder().decode([UploadResult].self, from: respData)
        guard let first = results.first else { throw APIError.decode }
        return first
    }

    // MARK: Sharing
    func createShare(_ body: [String: Any]) async throws -> ShareOut {
        try await send(makeRequest("api/shares", method: "POST", json: body), as: ShareOut.self)
    }
    func listShares() async throws -> [ShareOut] { try await get("api/shares", as: [ShareOut].self) }
    func deleteShare(_ id: Int) async throws { try await action("api/shares/\(id)", method: "DELETE") }

    // MARK: Chat
    func chatStatus() async throws -> ChatStatus { try await get("api/v1/chat/status", as: ChatStatus.self) }
    func chat(message: String, history: [ChatTurn], provider: String? = nil) async throws -> ChatReply {
        var body: [String: Any] = ["message": message,
                                   "history": history.map { ["role": $0.role, "content": $0.content] }]
        if let provider { body["provider"] = provider }
        return try await send(makeRequest("api/v1/chat", method: "POST", json: body), as: ChatReply.self)
    }
}

extension CharacterSet {
    static let urlQueryValueAllowed: CharacterSet = {
        var cs = CharacterSet.urlQueryAllowed; cs.remove(charactersIn: "&=+@"); return cs
    }()
}
