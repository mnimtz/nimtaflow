import SwiftUI

/// Browse albums (manual / smart / AI) and open one into a photo grid.
/// Reuses the same `Thumb` + `PhotoPager` the gallery uses, so an album opens
/// into the identical swipeable full-screen viewer.
struct AlbumsView: View {
    @EnvironmentObject var api: APIClient
    @State private var albums: [AlbumV1] = []
    @State private var loading = false
    @State private var error: String?
    @State private var showCreate = false
    @State private var newName = ""

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
            .navigationDestination(for: AlbumV1.self) { a in
                AlbumDetailView(album: a) { Task { await load() } }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { newName = ""; showCreate = true } label: { Image(systemName: "plus") }
                }
            }
            .alert("Neues Album", isPresented: $showCreate) {
                TextField("Name", text: $newName)
                Button("Erstellen") {
                    let n = newName.trimmingCharacters(in: .whitespaces)
                    if !n.isEmpty { Task { try? await api.createAlbum(name: n); await load() } }
                }
                Button("Abbrechen", role: .cancel) {}
            }
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
            Color.clear
                .aspectRatio(1, contentMode: .fit)        // fixed square cell
                .overlay {
                    if let c = album.cover_url { Thumb(url: api.url(c)) }
                    else {
                        Color.gray.opacity(0.18)
                            .overlay(Image(systemName: "photo.stack").font(.largeTitle).foregroundStyle(.secondary))
                    }
                }
                .clipped()
                .overlay(alignment: .bottomLeading) {
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
    var onChange: () -> Void = {}
    @Environment(\.dismiss) private var dismiss
    @State private var photos: [PhotoV1] = []
    @State private var cursor: Int? = nil
    @State private var hasMore = true
    @State private var loading = false
    @State private var selected: PhotoV1?
    @State private var showShare = false
    @State private var showRename = false
    @State private var renameText = ""
    @State private var displayName: String?

    let cols = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        PhotoGridView(photos: photos,
                      onReachEnd: { Task { await load() } },
                      removeLabel: "Aus Album entfernen",
                      onRemove: { p in
                          Task { try? await api.removeFromAlbum(album.id, photoId: p.id)
                                 photos.removeAll { $0.id == p.id }; onChange() }
                      })
        .navigationTitle(displayName ?? album.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button { showShare = true } label: { Label("Teilen", systemImage: "square.and.arrow.up") }
                    Button { renameText = displayName ?? album.name; showRename = true } label: {
                        Label("Umbenennen", systemImage: "pencil")
                    }
                    Button(role: .destructive) {
                        Task { try? await api.deleteAlbum(album.id); onChange(); dismiss() }
                    } label: { Label("Album löschen", systemImage: "trash") }
                } label: { Image(systemName: "ellipsis.circle") }
            }
        }
        .alert("Album umbenennen", isPresented: $showRename) {
            TextField("Name", text: $renameText)
            Button("Speichern") {
                let n = renameText.trimmingCharacters(in: .whitespaces)
                if !n.isEmpty { Task { try? await api.renameAlbum(album.id, name: n); displayName = n; onChange() } }
            }
            Button("Abbrechen", role: .cancel) {}
        }
        .task { if photos.isEmpty { await load() } }
        .sheet(isPresented: $showShare) {
            ShareSheetView(target: .album(id: album.id, title: displayName ?? album.name)).presentationDetents([.medium])
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
