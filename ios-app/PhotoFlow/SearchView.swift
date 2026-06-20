import SwiftUI

struct SearchView: View {
    @EnvironmentObject var api: APIClient
    @State private var query = ""
    @State private var results: [PhotoV1] = []
    @State private var loading = false
    @State private var searched = false
    @State private var selected: PhotoV1?

    let cols = [GridItem(.adaptive(minimum: 110), spacing: 2)]
    private let suggestions = ["Strand", "Geburtstag", "meine Ehefrau", "Bilder meiner Tochter", "Sonnenuntergang", "Weihnachten"]

    var body: some View {
        NavigationStack {
            Group {
                if loading {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if results.isEmpty && searched {
                    ContentUnavailableView("Keine Treffer", systemImage: "magnifyingglass",
                                           description: Text("Versuche andere Begriffe oder eine natürliche Frage."))
                } else if results.isEmpty {
                    suggestionList
                } else {
                    ScrollView {
                        LazyVGrid(columns: cols, spacing: 2) {
                            ForEach(results) { p in
                                PhotoTile(photo: p).onTapGesture { selected = p }
                            }
                        }.padding(2)
                    }
                }
            }
            .navigationTitle("Suche")
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always), prompt: "Suchen — z. B. „Bilder meiner Ehefrau\"")
            .onSubmit(of: .search) { Task { await run() } }
            .fullScreenCover(item: $selected) { p in PhotoPager(photos: results, start: p) }
        }
    }

    private var suggestionList: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                Text("VORSCHLÄGE").font(.caption.bold()).foregroundStyle(.secondary).padding(.top)
                FlowChips(items: suggestions) { s in query = s; Task { await run() } }
                Text("Tipp: Stelle „Ich bin: …“ auf der Beziehungen-Seite ein, dann funktionieren Begriffe wie „meine Ehefrau“ oder „mein Kollege“.")
                    .font(.caption).foregroundStyle(.secondary).padding(.top, 8)
            }.padding()
        }
    }

    func run() async {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return }
        loading = true; defer { loading = false }
        searched = true
        do { results = try await api.search(q).items } catch { results = [] }
    }
}

/// Simple wrapping chip row.
struct FlowChips: View {
    let items: [String]
    let onTap: (String) -> Void
    var body: some View {
        let cols = [GridItem(.adaptive(minimum: 110), spacing: 8)]
        LazyVGrid(columns: cols, alignment: .leading, spacing: 8) {
            ForEach(items, id: \.self) { s in
                Button { onTap(s) } label: {
                    Text(s).font(.callout).padding(.horizontal, 12).padding(.vertical, 7)
                        .background(.indigo.opacity(0.18), in: Capsule()).foregroundStyle(.indigo)
                }.buttonStyle(.plain)
            }
        }
    }
}
