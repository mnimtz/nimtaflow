import SwiftUI

/// What's being shared. Trips on iOS are auto-events (date range), so they map
/// to a trip share; albums/photos carry an id.
enum ShareTarget {
    case album(id: Int, title: String)
    case photo(id: Int, title: String)
    case trip(from: String, to: String, title: String)

    var kind: String { switch self { case .album: "album"; case .photo: "photo"; case .trip: "trip" } }
    var label: String { switch self { case .album: "Album"; case .photo: "Foto"; case .trip: "Reise" } }
    var title: String { switch self { case .album(_, let t), .photo(_, let t), .trip(_, _, let t): t } }
}

/// Create a public share link with optional password / expiry / download.
struct ShareSheetView: View {
    let target: ShareTarget
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss

    @State private var usePassword = false
    @State private var password = ""
    @State private var useExpiry = false
    @State private var expiresDays = 7
    @State private var allowDownload = true
    @State private var allowUpload = false
    @State private var creating = false
    @State private var result: ShareOut?
    @State private var error: String?
    @State private var copied = false

    var body: some View {
        NavigationStack {
            Form {
                if let s = result {
                    Section("Link erstellt") {
                        Text(s.url).font(.footnote).textSelection(.enabled)
                        Button { UIPasteboard.general.string = s.url; copied = true } label: {
                            Label(copied ? "Kopiert" : "Link kopieren", systemImage: copied ? "checkmark" : "doc.on.doc")
                        }
                        if let link = URL(string: s.url) {
                            ShareLink(item: link) { Label("Teilen…", systemImage: "square.and.arrow.up") }
                        }
                    }
                    Section {
                        Text("Wer den Link hat, kann das \(target.label) ansehen\(usePassword ? " (mit Passwort)" : "").")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                } else {
                    Section("Schutz") {
                        Toggle("Mit Passwort schützen", isOn: $usePassword)
                        if usePassword {
                            TextField("Passwort", text: $password).textInputAutocapitalization(.never).autocorrectionDisabled()
                        }
                        Toggle("Läuft ab", isOn: $useExpiry)
                        if useExpiry {
                            Picker("Ablauf", selection: $expiresDays) {
                                Text("1 Tag").tag(1); Text("7 Tage").tag(7)
                                Text("30 Tage").tag(30); Text("90 Tage").tag(90)
                            }
                        }
                    }
                    Section("Zugriff") {
                        Toggle("Download der Originale erlauben", isOn: $allowDownload)
                        if case .album = target {
                            Toggle("Gäste dürfen Fotos hinzufügen (Upload)", isOn: $allowUpload)
                        }
                    }
                    if let error { Section { Text(error).foregroundStyle(.red).font(.footnote) } }
                    Section {
                        Button { Task { await create() } } label: {
                            HStack { if creating { ProgressView() }; Text("Link erstellen") }
                        }.disabled(creating || (usePassword && password.isEmpty))
                    }
                }
            }
            .navigationTitle("\(target.label) teilen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Fertig") { dismiss() } } }
        }
    }

    func create() async {
        creating = true; defer { creating = false }; error = nil
        var body: [String: Any] = ["share_type": target.kind, "title": target.title,
                                   "allow_download": allowDownload]
        if usePassword && !password.isEmpty { body["password"] = password }
        if useExpiry { body["expires_days"] = expiresDays }
        switch target {
        case .album(let id, _): body["album_id"] = id; body["allow_upload"] = allowUpload
        case .photo(let id, _): body["photo_id"] = id
        case .trip(let from, let to, _): body["trip_from"] = from; body["trip_to"] = to
        }
        do { result = try await api.createShare(body) }
        catch { self.error = "Link konnte nicht erstellt werden." }
    }
}
