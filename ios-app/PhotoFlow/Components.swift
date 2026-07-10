import SwiftUI
import UIKit

// Shared in-memory image cache (decoded UIImages, fast path).
// countLimit ALLEIN reicht nicht: 800 dekodierte medium-Thumbnails (~256 KB)
// = ~200 MB — auf älteren Geräten Jetsam-kritisch. Zusätzliches totalCostLimit
// bei 128 MB kappt den Speicherverbrauch bei Beibehaltung des Cache-Nutzens.
private let imageCache: NSCache<NSURL, UIImage> = {
    let c = NSCache<NSURL, UIImage>()
    c.countLimit = 800
    c.totalCostLimit = 128 * 1024 * 1024
    return c
}()

/// Schätzt Kosten pro UIImage (Byte für dekodierten RGBA-Puffer).
private func imageCost(_ img: UIImage) -> Int {
    let w = Int(img.size.width * img.scale)
    let h = Int(img.size.height * img.scale)
    return max(w * h * 4, 4096)  // Mindestens 4 KB
}

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
    return URLSession(configuration: cfg, delegate: PFTrustDelegate(), delegateQueue: nil)
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
                        imageCache.setObject(img, forKey: url as NSURL, cost: imageCost(img))
                        if !Task.isCancelled { image = img; failed = false }
                        return
                    }
                    if code == 401 || code == 403 { if !Task.isCancelled { failed = true }; return }
                    // 404 (not ready) / 5xx → fall through to retry
                } catch is CancellationError { return }
                catch { /* network blip → retry */ }
                if attempt < delays.count {
                    // Task.sleep respektiert Cancellation. Wenn währenddessen
                    // die View verschwindet (schnelles Scrollen), wirft es
                    // CancellationError statt weitere 3s zu blockieren.
                    do { try await Task.sleep(nanoseconds: delays[attempt]) }
                    catch { return }
                }
            }
            if !Task.isCancelled { failed = true }
        }
    }
}

/// Warm the shared cache for a URL ahead of time (neighbour photos in the pager),
/// so swiping shows the next full-size image instantly instead of fetching on appear.
func prefetchImage(_ url: URL?, token: String) {
    guard let url, imageCache.object(forKey: url as NSURL) == nil else { return }
    var req = URLRequest(url: url)
    req.timeoutInterval = 20
    if !token.isEmpty { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
    Task.detached(priority: .utility) {
        if let (data, resp) = try? await imageSession.data(for: req),
           (200..<300).contains((resp as? HTTPURLResponse)?.statusCode ?? 0),
           let img = UIImage(data: data) {
            await MainActor.run { imageCache.setObject(img, forKey: url as NSURL, cost: imageCost(img)) }
        }
    }
}

/// Current on-disk image-cache size in MB (Settings label).
func imageCacheSizeMB() -> Int {
    Int((imageSession.configuration.urlCache?.currentDiskUsage ?? 0) / (1024 * 1024))
}

/// Clear the in-memory + on-disk image caches (Settings → "Cache leeren").
/// WICHTIG bei Logout: der URLCache legt Files im Cache-Directory ab, die auch
/// nach `removeAllCachedResponses` teilweise als tote Fragmente liegen können.
/// Wir räumen zusätzlich den Ordner `photoflow-thumbs` unter Caches auf.
@MainActor func clearImageCaches() {
    imageCache.removeAllObjects()
    imageSession.configuration.urlCache?.removeAllCachedResponses()
    if let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first {
        let dir = caches.appendingPathComponent("photoflow-thumbs")
        try? FileManager.default.removeItem(at: dir)
    }
}

/// Shimmer-Platzhalter für Thumb während des Ladens — sanft animierter Gradient.
private struct ShimmerView: View {
    @State private var phase: CGFloat = -1
    var body: some View {
        GeometryReader { _ in
            LinearGradient(
                stops: [
                    .init(color: Color(white: 0.18, opacity: 1), location: 0),
                    .init(color: Color(white: 0.28, opacity: 1), location: 0.4),
                    .init(color: Color(white: 0.18, opacity: 1), location: 1),
                ],
                startPoint: .init(x: phase, y: 0),
                endPoint: .init(x: phase + 1, y: 1)
            )
            .onAppear {
                withAnimation(.linear(duration: 1.2).repeatForever(autoreverses: false)) { phase = 1 }
            }
        }
    }
}

/// Authenticated async image that fills its frame (gallery thumbnails etc.).
struct Thumb: View {
    let url: URL?
    var contentMode: ContentMode = .fill
    var blurData: String? = nil
    @EnvironmentObject var api: APIClient
    @StateObject private var loader = AuthImageLoader()

    private var blurPlaceholder: UIImage? {
        guard let b64 = blurData, let data = Data(base64Encoded: b64) else { return nil }
        return UIImage(data: data)
    }

    var body: some View {
        Group {
            if let img = loader.image {
                Image(uiImage: img).resizable().aspectRatio(contentMode: contentMode)
            } else if loader.failed {
                Color(white: 0.15)
                    .overlay(Image(systemName: "photo").foregroundStyle(.secondary))
            } else if let blur = blurPlaceholder {
                Image(uiImage: blur).resizable().aspectRatio(contentMode: contentMode)
                    .overlay(ShimmerView().opacity(0.35))
            } else {
                ShimmerView()
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

/// THE one photo/video grid used across the app (albums, person, trips, search,
/// map drilldown) so every result list looks + behaves identically: uniform
/// square tiles, the same full-screen viewer (with details/share/rating), the
/// same pagination + optional long-press action. Gallery has its own variant only
/// because it adds date-section grouping.
/// Sort options offered by the shared grid toolbar. Maps to the backend `sort`
/// query param ("newest" is the default everywhere).
enum GridSort: String, CaseIterable, Identifiable {
    case newest, oldest
    var id: String { rawValue }
    var label: String { self == .newest ? "Neueste" : "Älteste" }
}

/// Media-type filter offered by the shared grid toolbar. `nil` = Alle.
enum GridMediaFilter: String, CaseIterable, Identifiable {
    case all, photos, videos
    var id: String { rawValue }
    var label: String { self == .all ? "Alle" : (self == .photos ? "Fotos" : "Videos") }
    /// Backend `media_type` value; nil means "no filter". Must be "photo"/"video"
    /// to match the API (it matches "photo", not "image" — "image" silently no-ops).
    var mediaType: String? { self == .photos ? "photo" : (self == .videos ? "video" : nil) }
}

struct PhotoGridView: View {
    let photos: [PhotoV1]
    var onReachEnd: (() -> Void)? = nil
    var removeLabel: String? = nil          // e.g. "Aus Album entfernen"
    var onRemove: ((PhotoV1) -> Void)? = nil
    // Optional sort/filter controls. When a binding is supplied a small toolbar
    // is shown above the grid; `onControlsChange` fires so the parent can re-fetch.
    var sort: Binding<GridSort>? = nil
    var mediaFilter: Binding<GridMediaFilter>? = nil
    var onControlsChange: (() -> Void)? = nil
    @State private var selected: PhotoV1?
    private let cols = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    private var showControls: Bool { sort != nil || mediaFilter != nil }

    var body: some View {
        ScrollView {
            if showControls {
                HStack(spacing: 8) {
                    if let sort {
                        Menu {
                            Picker("Sortierung", selection: sort) {
                                ForEach(GridSort.allCases) { Text($0.label).tag($0) }
                            }
                        } label: {
                            Label(sort.wrappedValue.label, systemImage: "arrow.up.arrow.down")
                                .font(.subheadline)
                        }
                    }
                    if let mediaFilter {
                        Menu {
                            Picker("Medientyp", selection: mediaFilter) {
                                ForEach(GridMediaFilter.allCases) { Text($0.label).tag($0) }
                            }
                        } label: {
                            Label(mediaFilter.wrappedValue.label, systemImage: "line.3.horizontal.decrease.circle")
                                .font(.subheadline)
                        }
                    }
                    Spacer()
                }
                .padding(.horizontal, 8).padding(.vertical, 6)
                .onChange(of: sort?.wrappedValue) { _, _ in onControlsChange?() }
                .onChange(of: mediaFilter?.wrappedValue) { _, _ in onControlsChange?() }
            }
            LazyVGrid(columns: cols, spacing: 2) {
                ForEach(photos) { p in
                    PhotoTile(photo: p)
                        .onTapGesture { selected = p }
                        .contextMenu {
                            if let onRemove, let removeLabel {
                                Button(role: .destructive) { onRemove(p) } label: {
                                    Label(removeLabel, systemImage: "minus.circle")
                                }
                            }
                        }
                        .onAppear { if p.id == photos.last?.id { onReachEnd?() } }
                }
            }
            .padding(2)
        }
        .fullScreenCover(item: $selected) { p in PhotoPager(photos: photos, start: p) }
    }
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
            .overlay { Thumb(url: api.url("api/photos/\(photo.id)/thumbnail?size=medium"), blurData: photo.blur_data) }
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
