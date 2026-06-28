import SwiftUI

/// Haustiere — photos the AI tagged as showing a pet (dog/cat/…). Mirrors the web
/// /pets view; reuses the shared full-screen pager via PhotoGridView.
struct PetsView: View {
    @EnvironmentObject var api: APIClient
    @State private var photos: [PhotoV1] = []
    @State private var cursor: Int? = nil
    @State private var hasMore = true
    @State private var loading = false
    @State private var loadedOnce = false

    var body: some View {
        NavigationStack {
            Group {
                if photos.isEmpty && loadedOnce {
                    ContentUnavailableView("Keine Haustier-Fotos",
                        systemImage: "pawprint",
                        description: Text("Sobald die KI Fotos beschrieben hat, erscheinen Hunde, Katzen & Co. hier."))
                } else {
                    PhotoGridView(photos: photos, onReachEnd: { Task { await load() } })
                }
            }
            .navigationTitle("Haustiere")
            .task { if !loadedOnce { await load() } }
        }
    }

    func load() async {
        guard hasMore, !loading else { return }
        loading = true; defer { loading = false; loadedOnce = true }
        do {
            let page = try await api.pets(cursor: cursor)
            photos += page.items
            cursor = page.next_cursor
            hasMore = page.has_more
        } catch { hasMore = false }
    }
}
