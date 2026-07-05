import SwiftUI

struct GalleryView: View {
    let api: APIClient
    var personId: Int? = nil
    var albumId: Int? = nil
    var title: String = "Galerie"

    @State private var photos: [PhotoV1] = []
    @State private var isLoading = false
    @State private var nextCursor: Int? = nil
    @State private var selectedPhoto: PhotoV1? = nil
    @State private var focusedId: Int? = nil

    private let columns = [GridItem(.adaptive(minimum: 320, maximum: 400), spacing: 24)]

    var body: some View {
        NavigationView {
            Group {
                if photos.isEmpty && isLoading {
                    ProgressView("Lade Fotos…")
                } else {
                    ScrollView {
                        LazyVGrid(columns: columns, spacing: 24) {
                            ForEach(photos) { photo in
                                Button {
                                    selectedPhoto = photo
                                } label: {
                                    PhotoCard(photo: photo, api: api)
                                }
                                .buttonStyle(.card)
                                .onAppear {
                                    if photo.id == photos.last?.id { Task { await loadMore() } }
                                }
                            }
                            if isLoading && !photos.isEmpty {
                                ProgressView()
                                    .gridCellColumns(columns.count)
                                    .frame(height: 80)
                            }
                        }
                        .padding(60)
                    }
                }
            }
            .navigationTitle(title)
        }
        .task { await loadMore() }
        .fullScreenCover(item: $selectedPhoto) { photo in
            MediaPlayerView(photo: photo, api: api, onClose: { selectedPhoto = nil })
        }
    }

    private func loadMore() async {
        guard !isLoading else { return }
        if !photos.isEmpty && nextCursor == nil { return }
        isLoading = true
        do {
            let page = try await api.fetchPhotos(cursor: nextCursor, limit: 60,
                                                  personId: personId, albumId: albumId)
            await MainActor.run {
                photos.append(contentsOf: page.items)
                nextCursor = page.next_cursor
                isLoading = false
            }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }
}
