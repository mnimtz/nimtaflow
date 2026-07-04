import SwiftUI

/// "Erinnerungen" — photos from exactly X years ago today, grouped by year.
/// Each group is a horizontal strip; tap a photo to open the full-screen pager.
struct MemoriesView: View {
    @EnvironmentObject var api: APIClient
    @State private var groups: [MemoryGroupV1] = []
    @State private var loading = false
    @State private var loadError: String?
    @State private var selected: PhotoV1?
    @State private var pagerItems: [PhotoV1] = []

    private func prefetchGroup(_ items: [PhotoV1]) {
        for p in items where !p.is_video {
            prefetchImage(api.url("api/photos/\(p.id)/thumbnail?size=large"), token: api.token)
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                if loading && groups.isEmpty { ProgressView().padding(.top, 60) }
                if let loadError, groups.isEmpty {
                    ContentUnavailableView {
                        Label("Erinnerungen konnten nicht geladen werden", systemImage: "exclamationmark.triangle")
                    } description: { Text(loadError) } actions: {
                        Button("Erneut versuchen") { Task { await load() } }
                    }.padding(.top, 60)
                } else if !loading && groups.isEmpty {
                    ContentUnavailableView("Keine Erinnerungen heute", systemImage: "sparkles",
                        description: Text("Hier erscheinen Fotos, die vor 1, 2, 3 … Jahren an diesem Tag entstanden sind."))
                        .padding(.top, 60)
                }
                LazyVStack(alignment: .leading, spacing: 22) {
                    ForEach(groups) { g in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(alignment: .firstTextBaseline) {
                                Text(g.years_ago == 1 ? "Vor 1 Jahr" : "Vor \(g.years_ago) Jahren")
                                    .font(.title3.bold())
                                Spacer()
                                Text(prettyDate(g.date)).font(.caption).foregroundStyle(.secondary)
                            }.padding(.horizontal)
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 6) {
                                    ForEach(g.items) { p in
                                        // Shared PhotoTile so the strip stays consistent with
                                        // every other grid (play + favourite badge, medium thumb).
                                        PhotoTile(photo: p)
                                            .frame(width: 140, height: 140)
                                            .clipShape(RoundedRectangle(cornerRadius: 12))
                                            .onTapGesture { pagerItems = g.items; selected = p }
                                    }
                                }.padding(.horizontal)
                            }
                        }
                    }
                }.padding(.vertical, 8)
            }
            .navigationTitle("Erinnerungen")
            .task { await load() }
            .refreshable { await load() }
            .fullScreenCover(item: $selected) { p in PhotoPager(photos: pagerItems, start: p) }
        }
    }

    func load() async {
        loading = true; defer { loading = false }
        do {
            groups = try await api.memories()
            loadError = nil
            // Pre-warm thumbnails so the first tap shows the image immediately.
            for g in groups { prefetchGroup(g.items) }
        }
        catch { loadError = (error as NSError).localizedDescription }
    }
}
