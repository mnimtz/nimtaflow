import SwiftUI

struct AlbumsView: View {
    let api: APIClient
    @State private var albums: [AlbumV1] = []
    @State private var isLoading = true

    private let columns = [GridItem(.adaptive(minimum: 280), spacing: 24)]

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    VStack(spacing: 16) { ProgressView(); Text("Lade Alben…").foregroundStyle(.secondary) }
                } else if albums.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "rectangle.stack").font(.system(size: 60)).foregroundStyle(.secondary)
                        Text("Keine Alben").foregroundStyle(.secondary)
                    }
                } else {
                    ScrollView {
                        LazyVGrid(columns: columns, spacing: 24) {
                            ForEach(albums) { album in
                                NavigationLink(destination: AlbumDetailView(album: album, api: api)) {
                                    AlbumCard(album: album, api: api)
                                }
                                .buttonStyle(.card)
                            }
                        }
                        .focusSection()
                        .padding(60)
                    }
                }
            }
            .navigationTitle("Alben")
        }
        .task {
            if let fetched = try? await api.fetchAlbums() {
                albums = fetched.sorted { $0.photo_count > $1.photo_count }
                isLoading = false
            }
        }
    }
}

struct AlbumCard: View {
    let album: AlbumV1
    let api: APIClient

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Group {
                if let cover = album.cover_url, let url = api.fixedURL(cover) {
                    AuthAsyncImage(url: url, headers: api.authHeaders()) { img in
                        img.resizable().aspectRatio(contentMode: .fill)
                    } placeholder: {
                        coverPlaceholder
                    }
                } else {
                    coverPlaceholder
                }
            }
            .frame(width: 280, height: 180)
            .clipped()

            VStack(alignment: .leading, spacing: 4) {
                Text(album.name).font(.headline).lineLimit(1)
                Text("\(album.photo_count) Fotos").font(.subheadline).foregroundStyle(.secondary)
            }
            .padding(12)
        }
        .background(Color.secondary.opacity(0.1), in: RoundedRectangle(cornerRadius: 12))
    }

    private var coverPlaceholder: some View {
        Rectangle().fill(Color.secondary.opacity(0.2))
            .overlay(Image(systemName: "rectangle.stack").font(.largeTitle).foregroundStyle(.secondary))
    }
}

struct AlbumDetailView: View {
    let album: AlbumV1
    let api: APIClient

    @State private var photos: [PhotoV1] = []
    @State private var isLoading = true
    @State private var hasMore = true
    @State private var nextCursor: Int? = nil

    private let columns = [GridItem(.adaptive(minimum: 280), spacing: 20)]

    var body: some View {
        Group {
            if isLoading && photos.isEmpty {
                VStack(spacing: 16) { ProgressView(); Text("Lade Fotos…").foregroundStyle(.secondary) }
            } else {
                ScrollView {
                    LazyVGrid(columns: columns, spacing: 20) {
                        ForEach(photos) { photo in
                            NavigationLink(destination: MediaPlayerView(photo: photo, photos: photos, api: api)) {
                                PhotoCard(photo: photo, api: api)
                            }
                            .buttonStyle(.card)
                        }
                    }
                    .focusSection()
                    .padding(60)

                    if hasMore {
                        Button("Mehr laden") { Task { await load() } }
                            .buttonStyle(.bordered).padding(20)
                    }
                }
            }
        }
        .navigationTitle(album.name)
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        if let page = try? await api.fetchAlbumPhotos(albumId: album.id, cursor: nextCursor) {
            photos += page.items
            nextCursor = page.next_cursor
            hasMore = page.has_more
        }
        isLoading = false
    }
}
