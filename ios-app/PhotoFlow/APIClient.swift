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

    private func makeRequest(_ path: String, method: String = "GET", json: Any? = nil) -> URLRequest {
        var req = URLRequest(url: base.appendingPathComponent(path))
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

    // Absolute URL for an image path that the API returned (already absolute) or a relative /api path.
    func url(_ s: String) -> URL? {
        if s.hasPrefix("http") { return URL(string: s) }
        return base.appendingPathComponent(s)
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
    func photos(cursor: Int?, favorites: Bool = false, mediaType: String? = nil) async throws -> PhotoPage {
        var p = "api/v1/photos?limit=60"
        if let cursor { p += "&cursor=\(cursor)" }
        if favorites { p += "&favorites=true" }
        if let mediaType { p += "&media_type=\(mediaType)" }
        return try await get(p, as: PhotoPage.self)
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
}

extension CharacterSet {
    static let urlQueryValueAllowed: CharacterSet = {
        var cs = CharacterSet.urlQueryAllowed; cs.remove(charactersIn: "&=+@"); return cs
    }()
}
