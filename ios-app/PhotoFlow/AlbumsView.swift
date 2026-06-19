import SwiftUI

/// Browse albums (manual / smart / AI) and open one into a photo grid.
/// Reuses the same `Thumb` + `PhotoPager` the gallery uses, so an album opens
/// into the identical swipeable full-screen viewer.
struct AlbumsView: View {
    @EnvironmentObject var api: APIClient
    @State private var albums: [AlbumV1] = []
    @State private var loading = false
    @State private var error: String?

    let cols = [GridItem(.adaptive(minimum: 150), spacing: 12)]

    var body: some View {
        NavigationStack {
            ScrollView {
                if let error { Text(error).foregroundStyle(.secondary).padding() }
                LazyVGrid(columns: cols, spacing: 14) {
                    ForEach(albums) { a in
                        NavigationLink(value: a) { AlbumCard(album: a) }
                            .buttonStyle(.plain)
                    }
                }
                .padding(12)
                if loading { ProgressView().padding() }
                if !loading && albums.isEmpty && error == nil {
                    ContentUnavailableView("Keine Alben", systemImage: "rectangle.stack",
                                           description: Text("Alben aus dem Web erscheinen hier automatisch."))
                        .padding(.top, 60)
                }
            }
            .navigationTitle("Alben")
            .navigationDestination(for: AlbumV1.self) { AlbumDetailView(album: $0) }
            .refreshable { await load() }
            .task { if albums.isEmpty { await load() } }
        }
    }

    func load() async {
        loading = true; defer { loading = false }
        do { albums = try await api.albums(); error = nil }
        catch { self.error = "Alben konnten nicht geladen werden." }
    }
}

private struct AlbumCard: View {
    @EnvironmentObject var api: APIClient
    let album: AlbumV1

    var typeIcon: String {
        switch album.album_type {
        case "smart": return "sparkles"
        case "ai": return "wand.and.stars"
        default: return "rectangle.stack.fill"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ZStack(alignment: .bottomLeading) {
                if let c = album.cover_url {
                    Thumb(url: api.url(c)).aspectRatio(1, contentMode: .fill)
                } else {
                    RoundedRectangle(cornerRadius: 0).fill(Color.gray.opacity(0.18))
                        .aspectRatio(1, contentMode: .fill)
                        .overlay(Image(systemName: "photo.stack").font(.largeTitle).foregroundStyle(.secondary))
                }
                Image(systemName: typeIcon)
                    .font(.caption).foregroundStyle(.white)
                    .padding(6).background(.black.opacity(0.45), in: Circle()).padding(8)
            }
            .clipShape(RoundedRectangle(cornerRadius: 14))
            Text(album.name).font(.subheadline.weight(.semibold)).lineLimit(1)
            Text("\(album.photo_count) Fotos").font(.caption).foregroundStyle(.secondary)
        }
    }
}

/// Photo grid for one album — paginated, opens the shared full-screen pager.
struct AlbumDetailView: View {
    @EnvironmentObject var api: APIClient
    let album: AlbumV1
    @State private var photos: [PhotoV1] = []
    @State private var cursor: Int? = nil
    @State private var hasMore = true
    @State private var loading = false
    @State private var selected: PhotoV1?
    @State private var showShare = false

    let cols = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: cols, spacing: 2) {
                ForEach(photos) { p in
                    Color.clear
                        .aspectRatio(1, contentMode: .fit)
                        .overlay { Thumb(url: api.url(p.thumb_medium_url)) }
                        .clipped()
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
        .navigationTitle(album.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showShare = true } label: { Image(systemName: "square.and.arrow.up") }
            }
        }
        .task { if photos.isEmpty { await load() } }
        .fullScreenCover(item: $selected) { p in PhotoPager(photos: photos, start: p) }
        .sheet(isPresented: $showShare) {
            ShareSheetView(target: .album(id: album.id, title: album.name)).presentationDetents([.medium])
        }
    }

    func load() async {
        guard hasMore, !loading else { return }
        loading = true; defer { loading = false }
        do {
            let page = try await api.albumPhotos(album.id, cursor: cursor)
            photos += page.items; cursor = page.next_cursor; hasMore = page.has_more
        } catch { hasMore = false }
    }
}
