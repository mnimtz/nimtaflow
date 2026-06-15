import SwiftUI

struct GalleryView: View {
    @EnvironmentObject var api: APIClient
    @State private var photos: [PhotoV1] = []
    @State private var cursor: Int? = nil
    @State private var hasMore = true
    @State private var loading = false
    @State private var favoritesOnly = false
    @State private var selected: PhotoV1?

    let cols = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVGrid(columns: cols, spacing: 2) {
                    ForEach(photos) { p in
                        Thumb(url: api.url(p.thumb_medium_url))
                            .aspectRatio(1, contentMode: .fill)
                            .frame(minHeight: 110)
                            .overlay(alignment: .topTrailing) {
                                if p.is_favorite { Image(systemName: "heart.fill").font(.caption2).foregroundStyle(.red).padding(4) }
                            }
                            .overlay(alignment: .bottomLeading) {
                                if p.is_video { Image(systemName: "play.fill").font(.caption2).foregroundStyle(.white).padding(4).shadow(radius: 2) }
                            }
                            .contentShape(Rectangle())
                            .onTapGesture { selected = p }
                            .onAppear { if p.id == photos.last?.id { Task { await load() } } }
                    }
                }
                .padding(2)
                if loading { ProgressView().padding() }
            }
            .navigationTitle("Galerie")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { favoritesOnly.toggle(); Task { await reload() } } label: {
                        Image(systemName: favoritesOnly ? "heart.fill" : "heart")
                    }
                }
            }
            .refreshable { await reload() }
            .task { if photos.isEmpty { await load() } }
            .fullScreenCover(item: $selected) { p in
                PhotoPager(photos: photos, start: p)
            }
        }
    }

    func reload() async { photos = []; cursor = nil; hasMore = true; await load() }
    func load() async {
        guard hasMore, !loading else { return }
        loading = true; defer { loading = false }
        do {
            let page = try await api.photos(cursor: cursor, favorites: favoritesOnly)
            photos += page.items; cursor = page.next_cursor; hasMore = page.has_more
        } catch { hasMore = false }
    }
}

/// Full-screen swipeable, zoomable photo viewer.
struct PhotoPager: View {
    @EnvironmentObject var api: APIClient
    let photos: [PhotoV1]
    let start: PhotoV1
    @Environment(\.dismiss) var dismiss
    @State private var index: Int = 0
    @State private var favs: Set<Int> = []

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()
            TabView(selection: $index) {
                ForEach(Array(photos.enumerated()), id: \.element.id) { i, p in
                    ZoomableImage(url: api.url(p.original_url) ?? api.url(p.thumb_medium_url)).tag(i)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            HStack(spacing: 18) {
                Button { Task { try? await api.toggleFavorite(photos[index].id); toggleLocal() } } label: {
                    Image(systemName: isFav ? "heart.fill" : "heart").foregroundStyle(isFav ? .red : .white)
                }
                Button { dismiss() } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.white) }
            }
            .font(.title2).padding()
        }
        .onAppear {
            index = photos.firstIndex(of: start) ?? 0
            favs = Set(photos.filter { $0.is_favorite }.map { $0.id })
        }
    }
    var isFav: Bool { favs.contains(photos[safe: index]?.id ?? -1) }
    func toggleLocal() { let id = photos[index].id; if favs.contains(id) { favs.remove(id) } else { favs.insert(id) } }
}

struct ZoomableImage: View {
    let url: URL?
    @State private var scale: CGFloat = 1
    var body: some View {
        Thumb(url: url)
            .aspectRatio(contentMode: .fit)
            .scaleEffect(scale)
            .gesture(MagnificationGesture().onChanged { scale = max(1, $0) }.onEnded { _ in withAnimation { scale = max(1, min(scale, 4)) } })
            .onTapGesture(count: 2) { withAnimation { scale = scale > 1 ? 1 : 2.5 } }
    }
}

extension Array { subscript(safe i: Int) -> Element? { indices.contains(i) ? self[i] : nil } }
