import SwiftUI
import UIKit

// Shared in-memory image cache (thread-safe).
private let imageCache: NSCache<NSURL, UIImage> = {
    let c = NSCache<NSURL, UIImage>(); c.countLimit = 600; return c
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
        if let cached = imageCache.object(forKey: url as NSURL) { image = cached; return }
        image = nil; failed = false
        task?.cancel()
        task = Task {
            var req = URLRequest(url: url)
            if !token.isEmpty { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
            do {
                let (data, resp) = try await URLSession.shared.data(for: req)
                let ok = (resp as? HTTPURLResponse).map { (200..<300).contains($0.statusCode) } ?? false
                guard ok, let img = UIImage(data: data) else { if !Task.isCancelled { failed = true }; return }
                imageCache.setObject(img, forKey: url as NSURL)
                if !Task.isCancelled { image = img }
            } catch { if !Task.isCancelled { failed = true } }
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
