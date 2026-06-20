import SwiftUI
import UIKit

// Shared in-memory image cache (decoded UIImages, fast path).
private let imageCache: NSCache<NSURL, UIImage> = {
    let c = NSCache<NSURL, UIImage>(); c.countLimit = 800; return c
}()

// Dedicated URLSession with a big on-DISK cache. Thumbnails are served with a
// long immutable Cache-Control, so once fetched they're reused from disk across
// scrolls AND app launches — no constant re-fetching = no more grey-placeholder
// dropouts under load. Backs the in-memory NSCache.
private let imageSession: URLSession = {
    let cache = URLCache(memoryCapacity: 64 * 1024 * 1024,      // 64 MB RAM
                         diskCapacity: 1024 * 1024 * 1024,      // 1 GB disk
                         diskPath: "photoflow-thumbs")
    let cfg = URLSessionConfiguration.default
    cfg.urlCache = cache
    cfg.requestCachePolicy = .returnCacheDataElseLoad
    cfg.httpMaximumConnectionsPerHost = 8
    cfg.timeoutIntervalForRequest = 20
    return URLSession(configuration: cfg)
}()

/// Loads an image with the Bearer token (the server enforces login, so plain
/// AsyncImage would 401). Caches decoded images in memory.
@MainActor
final class AuthImageLoader: ObservableObject {
    @Published var image: UIImage?
    @Published var failed = false
    private var task: Task<Void, Never>?

    func load(_ url: URL?, token: String) {
        guard let url else { failed = true; return }
        if let cached = imageCache.object(forKey: url as NSURL) { image = cached; failed = false; return }
        image = nil; failed = false
        task?.cancel()
        task = Task {
            var req = URLRequest(url: url)
            req.timeoutInterval = 20
            if !token.isEmpty { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
            // Retry transient failures with backoff: a thumbnail still being
            // generated returns 404 ("not ready"), and server load / network blips
            // are momentary. Without this they'd show as a permanent grey box during
            // bulk processing. 401/403 (auth) are NOT retried.
            let delays: [UInt64] = [400_000_000, 1_200_000_000, 3_000_000_000]  // 0.4s, 1.2s, 3s
            for attempt in 0...delays.count {
                if Task.isCancelled { return }
                do {
                    let (data, resp) = try await imageSession.data(for: req)
                    let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                    if (200..<300).contains(code), let img = UIImage(data: data) {
                        imageCache.setObject(img, forKey: url as NSURL)
                        if !Task.isCancelled { image = img; failed = false }
                        return
                    }
                    if code == 401 || code == 403 { if !Task.isCancelled { failed = true }; return }
                    // 404 (not ready) / 5xx → fall through to retry
                } catch is CancellationError { return }
                catch { /* network blip → retry */ }
                if attempt < delays.count { try? await Task.sleep(nanoseconds: delays[attempt]) }
            }
            if !Task.isCancelled { failed = true }
        }
    }
}

/// Authenticated async image that fills its frame (gallery thumbnails etc.).
struct Thumb: View {
    let url: URL?
    var contentMode: ContentMode = .fill
    @EnvironmentObject var api: APIClient
    @StateObject private var loader = AuthImageLoader()

    var body: some View {
        Group {
            if let img = loader.image {
                Image(uiImage: img).resizable().aspectRatio(contentMode: contentMode)
            } else if loader.failed {
                Color.gray.opacity(0.18).overlay(Image(systemName: "photo").foregroundStyle(.secondary))
            } else {
                Color.gray.opacity(0.12).overlay(ProgressView())
            }
        }
        .clipped()
        .task(id: url) { loader.load(url, token: api.token) }
    }
}

struct Avatar: View {
    let url: URL?
    let initials: String
    var size: CGFloat = 56
    @EnvironmentObject var api: APIClient
    @StateObject private var loader = AuthImageLoader()

    var body: some View {
        ZStack {
            Circle().fill(LinearGradient(colors: [.indigo, .purple], startPoint: .topLeading, endPoint: .bottomTrailing))
            if let img = loader.image {
                Image(uiImage: img).resizable().scaledToFill()
            } else {
                Text(initials).font(.system(size: size * 0.4, weight: .semibold)).foregroundStyle(.white)
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .task(id: url) { loader.load(url, token: api.token) }
    }
}

extension String {
    var firstInitial: String { String(prefix(1)).uppercased() }
}

/// Reusable square photo/video tile — the one true grid cell used everywhere
/// (gallery, search, albums, trips, person, …) so results always look uniform.
/// Color.clear sets the square size; the image fills + is clipped → never overflows.
struct PhotoTile: View {
    @EnvironmentObject var api: APIClient
    let photo: PhotoV1
    var body: some View {
        Color.clear
            .aspectRatio(1, contentMode: .fit)
            .overlay { Thumb(url: api.url("api/photos/\(photo.id)/thumbnail?size=medium")) }
            .clipped()
            .overlay(alignment: .bottomLeading) {
                if photo.is_video {
                    Image(systemName: "play.fill").font(.caption2).foregroundStyle(.white)
                        .padding(4).shadow(radius: 2)
                }
            }
            .overlay(alignment: .topTrailing) {
                if photo.is_favorite {
                    Image(systemName: "heart.fill").font(.caption2).foregroundStyle(.red).padding(4)
                }
            }
            .contentShape(Rectangle())
    }
}
