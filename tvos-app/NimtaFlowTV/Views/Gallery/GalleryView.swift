import SwiftUI

struct GalleryView: View {
    let api: APIClient

    @State private var photos: [PhotoV1] = []
    @State private var isLoading = true
    @State private var hasMore = true
    @State private var nextCursor: Int? = nil

    private let columns = [GridItem(.adaptive(minimum: 280), spacing: 20)]

    private var grouped: [(String, [PhotoV1])] {
        let dict = Dictionary(grouping: photos) { DateUtils.monthKey($0.taken_at) }
        return dict.sorted {
            if $0.key == "0000-00" { return false }
            if $1.key == "0000-00" { return true }
            return $0.key > $1.key
        }
    }

    var body: some View {
        NavigationStack {
            Group {
                if isLoading && photos.isEmpty {
                    VStack(spacing: 16) {
                        ProgressView()
                        Text("Lade Fotos…").foregroundStyle(.secondary)
                    }
                } else if photos.isEmpty {
                    emptyState
                } else {
                    scrollContent
                }
            }
            .navigationTitle("Galerie")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    if isLoading && !photos.isEmpty {
                        ProgressView().scaleEffect(0.8)
                    }
                }
            }
        }
        .task { await load() }
    }

    private var scrollContent: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 40) {
                ForEach(grouped, id: \.0) { key, group in
                    VStack(alignment: .leading, spacing: 16) {
                        Text(key == "0000-00" ? "Kein Datum" : DateUtils.monthYear(key + "-01"))
                            .font(.title2).bold()
                            .padding(.horizontal, 60)

                        LazyVGrid(columns: columns, spacing: 20) {
                            ForEach(group) { photo in
                                NavigationLink(destination: MediaPlayerView(photo: photo, photos: group, api: api)) {
                                    PhotoCard(photo: photo, api: api)
                                }
                                .buttonStyle(.card)
                            }
                        }
                        .focusSection()
                        .padding(.horizontal, 60)
                    }
                }

                if hasMore {
                    HStack {
                        Spacer()
                        Button("Mehr laden") { Task { await load() } }
                            .buttonStyle(.bordered)
                        Spacer()
                    }
                    .padding(40)
                }
            }
            .padding(.vertical, 40)
        }
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 60)).foregroundStyle(.secondary)
            Text("Keine Fotos").foregroundStyle(.secondary)
        }
    }

    private func load() async {
        guard hasMore || photos.isEmpty else { return }
        isLoading = true
        if let page = try? await api.fetchPhotos(cursor: nextCursor, limit: 60) {
            photos += page.items
            nextCursor = page.next_cursor
            hasMore = page.has_more
        }
        isLoading = false
    }
}
