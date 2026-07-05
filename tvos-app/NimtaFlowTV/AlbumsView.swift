import SwiftUI

struct AlbumsView: View {
    let api: APIClient
    @State private var albums: [AlbumV1] = []
    @State private var isLoading = true
    @State private var selectedAlbum: AlbumV1? = nil

    private let columns = [GridItem(.adaptive(minimum: 360, maximum: 440), spacing: 32)]

    var body: some View {
        NavigationView {
            Group {
                if isLoading {
                    ProgressView("Lade Alben…")
                } else if albums.isEmpty {
                    Label("Keine Alben vorhanden", systemImage: "rectangle.stack")
                        .font(.title2)
                        .foregroundStyle(.secondary)
                } else {
                    ScrollView {
                        LazyVGrid(columns: columns, spacing: 32) {
                            ForEach(albums) { album in
                                Button { selectedAlbum = album } label: {
                                    AlbumCard(album: album, api: api)
                                }
                                .buttonStyle(.card)
                            }
                        }
                        .padding(60)
                    }
                }
            }
            .navigationTitle("Alben")
        }
        .task {
            albums = (try? await api.fetchAlbums()) ?? []
            isLoading = false
        }
        .fullScreenCover(item: $selectedAlbum) { album in
            NavigationView {
                GalleryView(api: api, albumId: album.id, title: album.name)
                    .toolbar {
                        ToolbarItem(placement: .navigationBarLeading) {
                            Button("Schließen") { selectedAlbum = nil }
                        }
                    }
            }
            .onExitCommand { selectedAlbum = nil }
        }
    }
}

private struct AlbumCard: View {
    let album: AlbumV1
    let api: APIClient

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Group {
                if let coverURL = album.cover_url, let url = api.fixedURL(coverURL) {
                    AuthAsyncImage(url: url, headers: api.authHeaders()) { img in
                        img.resizable().aspectRatio(contentMode: .fill)
                    } placeholder: {
                        Rectangle().fill(Color.indigo.opacity(0.3))
                            .overlay(Image(systemName: "rectangle.stack")
                                .font(.largeTitle).foregroundStyle(.white.opacity(0.5)))
                    }
                } else {
                    Rectangle().fill(Color.indigo.opacity(0.2))
                        .overlay(Image(systemName: "rectangle.stack")
                            .font(.largeTitle).foregroundStyle(.indigo.opacity(0.6)))
                }
            }
            .frame(width: 360, height: 220)
            .clipped()

            VStack(alignment: .leading, spacing: 4) {
                Text(album.name)
                    .font(.headline)
                    .foregroundStyle(.white)
                    .lineLimit(1)
                Text("\(album.photo_count) Fotos")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .padding(16)
        }
        .background(Color.white.opacity(0.06))
        .cornerRadius(16)
    }
}
