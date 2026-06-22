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

    /// On 401, refresh the access token with the stored refresh token (long-lived)
    /// and retry once — so an expired access token NEVER forces a re-login. Returns
    /// false if there's no refresh token or the refresh itself failed.
    private func refreshToken() async -> Bool {
        guard !refresh.isEmpty else { return false }
        // Percent-encode the token: JWTs are URL-safe today, but a reserved char
        // would otherwise silently break refresh → spurious force-logout.
        let enc = refresh.addingPercentEncoding(withAllowedCharacters: .urlQueryValueAllowed) ?? refresh
        var req = URLRequest(url: absoluteURL("api/auth/refresh?refresh_token=\(enc)"))
        req.httpMethod = "POST"
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard (200..<300).contains((resp as? HTTPURLResponse)?.statusCode ?? 0) else { return false }
            let tok = try JSONDecoder().decode(TokenResponse.self, from: data)
            token = tok.access_token; refresh = tok.refresh_token
            return true
        } catch { return false }
    }

    @discardableResult
    func send<T: Decodable>(_ request: URLRequest, as type: T.Type, allowRetry: Bool = true) async throws -> T {
        let (data, resp) = try await URLSession.shared.data(for: request)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 {
            if allowRetry, await refreshToken() {
                var r = request; r.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                return try await send(r, as: type, allowRetry: false)
            }
            await logout(); throw APIError.status(401)
        }
        guard (200..<300).contains(code) else { throw APIError.status(code) }
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw APIError.decode }
    }

    @discardableResult
    func action(_ path: String, method: String, json: Any? = nil, allowRetry: Bool = true) async throws -> Bool {
        let (_, resp) = try await URLSession.shared.data(for: makeRequest(path, method: method, json: json))
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if code == 401 {
            if allowRetry, await refreshToken() {
                return try await action(path, method: method, json: json, allowRetry: false)
            }
            await logout(); throw APIError.status(401)
        }
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
    func personPhotos(_ id: Int, cursor: Int?, sort: String? = nil, mediaType: String? = nil) async throws -> PhotoPage {
        var p = "api/v1/people/\(id)/photos?limit=60"; if let cursor { p += "&cursor=\(cursor)" }
        if let sort { p += "&sort=\(sort)" }
        if let mediaType { p += "&media_type=\(mediaType)" }
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
    func deletePerson(_ id: Int) async throws { try await action("api/people/\(id)", method: "DELETE") }
    func setAsMe(_ personId: Int) async throws { try await action("api/people/\(personId)/set-as-me", method: "POST") }

    // MARK: Single photo
    func photo(_ id: Int) async throws -> PhotoV1 { try await get("api/v1/photos/\(id)", as: PhotoV1.self) }
    func setRating(_ id: Int, rating: Int) async throws { try await action("api/v1/photos/\(id)/rating?rating=\(rating)", method: "PATCH") }
    func reprocess(_ id: Int) async throws { try await action("api/photos/\(id)/reprocess", method: "POST") }
    func photoFaces(_ id: Int) async throws -> [PhotoFace] { try await get("api/v1/photos/\(id)/faces", as: [PhotoFace].self) }
    func setProfileFace(personId: Int, faceId: Int) async throws {
        try await action("api/people/\(personId)/profile-face/\(faceId)", method: "POST")
    }
    func archivePhoto(_ id: Int) async throws { try await action("api/photos/\(id)/archive", method: "PATCH") }
    func trashPhoto(_ id: Int) async throws { try await action("api/photos/\(id)/trash", method: "PATCH") }
    func deletePhoto(_ id: Int) async throws { try await action("api/v1/photos/\(id)", method: "DELETE") }
    func photoDetail(_ id: Int) async throws -> PhotoDetailV1 { try await get("api/v1/photos/\(id)/detail", as: PhotoDetailV1.self) }
    func batch(_ action: String, ids: [Int]) async throws {
        try await self.action("api/photos/batch", method: "POST", json: ["action": action, "ids": ids])
    }
    func addPhotosToAlbum(_ albumId: Int, photoIds: [Int]) async throws {
        try await action("api/albums/\(albumId)/photos", method: "POST", json: ["photo_ids": photoIds])
    }

    // MARK: Albums
    func albums() async throws -> [AlbumV1] { try await get("api/v1/albums", as: [AlbumV1].self) }
    func albumPhotos(_ id: Int, cursor: Int?, sort: String? = nil) async throws -> PhotoPage {
        var p = "api/v1/albums/\(id)/photos?limit=60"; if let cursor { p += "&cursor=\(cursor)" }
        if let sort { p += "&sort=\(sort)" }
        return try await get(p, as: PhotoPage.self)
    }
    func createAlbum(name: String, type: String = "manual",
                     smartCriteria: [String: Any]? = nil, aiPrompt: String? = nil) async throws {
        var body: [String: Any] = ["name": name, "album_type": type]
        if let smartCriteria { body["smart_criteria"] = smartCriteria }
        if let aiPrompt { body["ai_prompt"] = aiPrompt }
        try await action("api/albums", method: "POST", json: body)
    }
    func renameAlbum(_ id: Int, name: String) async throws {
        try await action("api/albums/\(id)", method: "PATCH", json: ["name": name])
    }
    /// Full album edit: name + type + criteria. Server repopulates smart albums
    /// (no 1000-Limit) when the type or criteria change.
    func updateAlbum(_ id: Int, name: String, type: String,
                     smartCriteria: [String: Any]? = nil, aiPrompt: String? = nil) async throws {
        var body: [String: Any] = ["name": name, "album_type": type]
        if let smartCriteria { body["smart_criteria"] = smartCriteria }
        if let aiPrompt { body["ai_prompt"] = aiPrompt }
        try await action("api/albums/\(id)", method: "PATCH", json: body)
    }
    func refreshAlbum(_ id: Int) async throws { try await action("api/albums/\(id)/refresh", method: "POST") }
    func deleteAlbum(_ id: Int) async throws { try await action("api/albums/\(id)", method: "DELETE") }
    func removeFromAlbum(_ albumId: Int, photoId: Int) async throws {
        try await action("api/albums/\(albumId)/photos/\(photoId)", method: "DELETE")
    }

    func photosByDate(from: String, to: String, cursor: Int?) async throws -> PhotoPage {
        var p = "api/v1/photos?limit=60&date_from=\(from)&date_to=\(to)"
        if let cursor { p += "&cursor=\(cursor)" }
        return try await get(p, as: PhotoPage.self)
    }

    // MARK: Trip planner (Gemini)
    func planTrip(description: String, dateFrom: String?, dateTo: String?, tripType: String? = nil) async throws -> TripPlan {
        var body: [String: Any] = ["description": description]
        if let dateFrom { body["date_from"] = dateFrom }
        if let dateTo { body["date_to"] = dateTo }
        if let tripType { body["trip_type"] = tripType }
        var req = makeRequest("api/photos/plan-trip", method: "POST", json: body)
        req.timeoutInterval = 120   // grounded search can take longer
        return try await send(req, as: TripPlan.self)
    }
    func deleteTrip(_ albumId: Int) async throws { try await action("api/albums/\(albumId)", method: "DELETE") }
    func createTrip(_ plan: TripPlan) async throws -> CreateTripResult {
        var body: [String: Any] = ["name": plan.name, "description": plan.summary ?? ""]
        if let f = plan.date_from { body["date_from"] = f }
        if let t = plan.date_to { body["date_to"] = t }
        body["waypoints"] = plan.waypoints.map { w -> [String: Any] in
            var d: [String: Any] = ["place": w.place]
            if let c = w.country { d["country"] = c }
            if let dt = w.date { d["date"] = dt }
            if let la = w.lat { d["lat"] = la }
            if let ln = w.lng { d["lng"] = ln }
            if let n = w.note { d["note"] = n }
            return d
        }
        return try await send(makeRequest("api/photos/create-trip", method: "POST", json: body), as: CreateTripResult.self)
    }

    // MARK: Trips / events
    func trips(tripsOnly: Bool = false, minPhotos: Int? = nil) async throws -> TripsV1 {
        var p = "api/v1/trips?trips_only=\(tripsOnly)"
        if let minPhotos { p += "&min_photos=\(minPhotos)" }
        return try await get(p, as: TripsV1.self)
    }

    // MARK: Library stats
    func libraryStats() async throws -> LibraryStats { try await get("api/v1/stats", as: LibraryStats.self) }
    func scanProgress() async throws -> ScanProgress { try await get("api/sources/scan-progress", as: ScanProgress.self) }

    // MARK: Memories
    func memories() async throws -> [MemoryGroupV1] { try await get("api/v1/memories", as: [MemoryGroupV1].self) }

    // MARK: Map
    func mapPoints() async throws -> [MapPointV1] { try await get("api/v1/map", as: [MapPointV1].self) }
    func mapClusters(minLat: Double, minLng: Double, maxLat: Double, maxLng: Double, grid: Int) async throws -> [MapClusterV1] {
        let p = "api/v1/map/clusters?min_lat=\(minLat)&min_lng=\(minLng)&max_lat=\(maxLat)&max_lng=\(maxLng)&grid=\(grid)"
        return try await get(p, as: [MapClusterV1].self)
    }
    func mapPhotos(minLat: Double, minLng: Double, maxLat: Double, maxLng: Double) async throws -> [PhotoV1] {
        let p = "api/v1/map/photos?min_lat=\(minLat)&min_lng=\(minLng)&max_lat=\(maxLat)&max_lng=\(maxLng)"
        return try await get(p, as: PhotoPage.self).items
    }

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
    func updateShare(_ id: Int, title: String?, allowDownload: Bool?, expiresDays: Int?, password: String?) async throws {
        var body: [String: Any] = [:]
        if let title { body["title"] = title }
        if let allowDownload { body["allow_download"] = allowDownload }
        if let expiresDays { body["expires_days"] = expiresDays }
        if let password { body["password"] = password }
        try await action("api/shares/\(id)", method: "PATCH", json: body)
    }

    // MARK: Dashboard
    func dashboard() async throws -> DashboardV1 { try await get("api/v1/dashboard", as: DashboardV1.self) }

    // MARK: Highlights (video assistant)
    private struct MottosWrap: Decodable { let mottos: [MottoV1] }
    func mottos() async throws -> [MottoV1] { try await get("api/highlights/mottos", as: MottosWrap.self).mottos }
    func highlights() async throws -> [HighlightV1] { try await get("api/highlights", as: [HighlightV1].self) }
    func createHighlight(motto: String, title: String?, durationSec: Double,
                         personId: Int? = nil, personId2: Int? = nil, personIds: [Int]? = nil,
                         year: Int? = nil, albumId: Int? = nil, season: String? = nil) async throws -> HighlightV1 {
        var body: [String: Any] = ["motto": motto, "duration_sec": durationSec]
        if let title, !title.isEmpty { body["title"] = title }
        if let personId { body["person_id"] = personId }
        if let personId2 { body["person_id2"] = personId2 }
        if let personIds, !personIds.isEmpty { body["person_ids"] = personIds }
        if let year { body["year"] = year }
        if let albumId { body["album_id"] = albumId }
        if let season { body["season"] = season }
        return try await send(makeRequest("api/highlights", method: "POST", json: body), as: HighlightV1.self)
    }
    func deleteHighlight(_ id: Int) async throws { try await action("api/highlights/\(id)", method: "DELETE") }
    /// External video-AI: animate one photo (optionally with a creative scene prompt).
    @discardableResult
    func animatePhoto(_ photoId: Int, prompt: String? = nil) async throws -> Bool {
        var body: [String: Any] = ["photo_id": photoId]
        if let prompt, !prompt.isEmpty { body["prompt"] = prompt }
        return try await action("api/highlights/animate-photo", method: "POST", json: body)
    }

    // MARK: Face suggestions
    func faceSuggestions() async throws -> SuggestionGroups {
        try await get("api/people/faces/suggestions", as: SuggestionGroups.self)
    }
    func confirmAllSuggestions(personId: Int) async throws { try await action("api/people/suggestions/confirm/\(personId)", method: "POST") }
    func rejectAllSuggestions(personId: Int) async throws { try await action("api/people/suggestions/reject/\(personId)", method: "POST") }
    func confirmSuggestion(faceId: Int) async throws { try await action("api/people/faces/\(faceId)/confirm-suggestion", method: "POST") }
    func rejectSuggestion(faceId: Int) async throws { try await action("api/people/faces/\(faceId)/reject-suggestion", method: "POST") }

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
