import SwiftUI

/// Manage active public share links — copy or revoke.
struct SharesListView: View {
    @EnvironmentObject var api: APIClient
    @State private var shares: [ShareOut] = []
    @State private var loading = false
    @State private var copiedId: Int?

    func typeLabel(_ t: String) -> String { t == "album" ? "Album" : t == "photo" ? "Foto" : "Reise" }

    var body: some View {
        NavigationStack {
            List {
                if shares.isEmpty && !loading {
                    ContentUnavailableView("Keine geteilten Links", systemImage: "link",
                        description: Text("Teile ein Album, Foto oder eine Reise über das Teilen-Symbol."))
                }
                ForEach(shares) { s in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(typeLabel(s.share_type)).font(.caption).padding(.horizontal, 6).padding(.vertical, 2)
                                .background(.indigo.opacity(0.15), in: Capsule()).foregroundStyle(.indigo)
                            Text(s.title ?? "Geteilt").font(.subheadline.weight(.medium)).lineLimit(1)
                        }
                        Text(detail(s)).font(.caption).foregroundStyle(.secondary)
                        Text(s.url).font(.caption2).foregroundStyle(.tertiary).lineLimit(1)
                    }
                    .swipeActions(edge: .trailing) {
                        Button(role: .destructive) { Task { await revoke(s) } } label: { Label("Widerrufen", systemImage: "trash") }
                        Button { UIPasteboard.general.string = s.url; copiedId = s.id } label: { Label("Kopieren", systemImage: "doc.on.doc") }.tint(.indigo)
                    }
                    .overlay(alignment: .trailing) {
                        if copiedId == s.id { Text("kopiert").font(.caption2).foregroundStyle(.green) }
                    }
                }
            }
            .navigationTitle("Geteilte Links")
            .refreshable { await load() }
            .task { await load() }
            .overlay { if loading && shares.isEmpty { ProgressView() } }
        }
    }

    func detail(_ s: ShareOut) -> String {
        var parts: [String] = []
        if s.has_password { parts.append("🔒 Passwort") }
        if let e = s.expires_at { parts.append("läuft ab \(String(e.prefix(10)))") }
        parts.append(s.allow_download ? "Download an" : "nur ansehen")
        parts.append("\(s.view_count)× aufgerufen")
        return parts.joined(separator: " · ")
    }

    func load() async {
        loading = true; defer { loading = false }
        shares = (try? await api.listShares()) ?? []
    }
    func revoke(_ s: ShareOut) async {
        try? await api.deleteShare(s.id)
        await load()
    }
}
