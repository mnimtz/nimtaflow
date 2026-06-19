import SwiftUI

/// "Erinnerungen" — photos from exactly X years ago today, grouped by year.
/// Each group is a horizontal strip; tap a photo to open the full-screen pager.
struct MemoriesView: View {
    @EnvironmentObject var api: APIClient
    @State private var groups: [MemoryGroupV1] = []
    @State private var loading = false
    @State private var selected: PhotoV1?
    @State private var pagerItems: [PhotoV1] = []

    var body: some View {
        NavigationStack {
            ScrollView {
                if loading && groups.isEmpty { ProgressView().padding(.top, 60) }
                if !loading && groups.isEmpty {
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
                                        Thumb(url: api.url("api/photos/\(p.id)/thumbnail?size=medium"))
                                            .frame(width: 140, height: 140)
                                            .clipShape(RoundedRectangle(cornerRadius: 12))
                                            .overlay(alignment: .bottomLeading) {
                                                if p.is_video { Image(systemName: "play.fill").font(.caption2).foregroundStyle(.white).padding(5) }
                                            }
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
        groups = (try? await api.memories()) ?? []
    }
}
