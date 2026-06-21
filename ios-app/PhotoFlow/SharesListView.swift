import SwiftUI

/// Manage active public share links — copy or revoke.
struct SharesListView: View {
    @EnvironmentObject var api: APIClient
    @State private var shares: [ShareOut] = []
    @State private var loading = false
    @State private var copiedId: Int?
    @State private var editing: ShareOut?

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
                        Button { editing = s } label: { Label("Bearbeiten", systemImage: "pencil") }.tint(.orange)
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
            .sheet(item: $editing) { s in
                EditShareSheet(share: s) { await load() }
                    .presentationDetents([.medium])
            }
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

/// Edit an existing share link — title, expiry, download permission and an
/// optional new password. Calls api.updateShare(...).
private struct EditShareSheet: View {
    @EnvironmentObject var api: APIClient
    let share: ShareOut
    let onSaved: () async -> Void
    @Environment(\.dismiss) var dismiss

    @State private var title: String
    @State private var allowDownload: Bool
    @State private var setExpiry: Bool
    @State private var expiresDays: Int
    @State private var setPassword: Bool
    @State private var password = ""
    @State private var busy = false

    init(share: ShareOut, onSaved: @escaping () async -> Void) {
        self.share = share
        self.onSaved = onSaved
        _title = State(initialValue: share.title ?? "")
        _allowDownload = State(initialValue: share.allow_download)
        _setExpiry = State(initialValue: false)
        _expiresDays = State(initialValue: 30)
        _setPassword = State(initialValue: false)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Titel") {
                    TextField("Titel", text: $title)
                }
                Section("Zugriff") {
                    Toggle("Download erlauben", isOn: $allowDownload)
                }
                Section("Ablauf") {
                    Toggle("Ablaufdatum setzen", isOn: $setExpiry)
                    if setExpiry {
                        Stepper(value: $expiresDays, in: 1...365) {
                            HStack { Text("Läuft ab in"); Spacer()
                                Text("\(expiresDays) Tagen").foregroundStyle(.secondary) }
                        }
                    }
                }
                Section("Passwort") {
                    Toggle(share.has_password ? "Passwort ändern" : "Passwort setzen", isOn: $setPassword)
                    if setPassword {
                        SecureField("Neues Passwort", text: $password)
                    }
                }
                Section {
                    Button {
                        Task { await save() }
                    } label: {
                        HStack { if busy { ProgressView() }; Text("Speichern") }
                    }.disabled(busy)
                }
            }
            .navigationTitle("Link bearbeiten")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Schließen") { dismiss() } } }
        }
    }

    func save() async {
        busy = true; defer { busy = false }
        let t = title.trimmingCharacters(in: .whitespaces)
        try? await api.updateShare(share.id,
                                   title: t.isEmpty ? nil : t,
                                   allowDownload: allowDownload,
                                   expiresDays: setExpiry ? expiresDays : nil,
                                   password: (setPassword && !password.isEmpty) ? password : nil)
        await onSaved()
        dismiss()
    }
}
