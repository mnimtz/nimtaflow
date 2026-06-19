import SwiftUI

/// Gallery filter + sort — mirrors the web FilterPanel (sort newest/oldest/added/
/// name, media type photo/video/raw, filter by person).
struct GalleryFilterSheet: View {
    @Binding var sort: String
    @Binding var mediaType: String?
    @Binding var personId: Int?
    @Binding var personName: String?
    let onApply: () -> Void

    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss
    @State private var people: [PersonV1] = []
    @State private var personSearch = ""

    private let sorts: [(String, String)] = [
        ("newest", "Neueste zuerst"), ("oldest", "Älteste zuerst"),
        ("added", "Zuletzt hinzugefügt"), ("name", "Dateiname"),
    ]
    private let media: [(String?, String)] = [
        (nil, "Alle"), ("photo", "Nur Fotos"), ("video", "Nur Videos"), ("raw", "Nur RAW"),
    ]
    private var namedPeople: [PersonV1] {
        let n = people.filter { !$0.name.isEmpty && $0.name != "Unbekannt" }
        guard !personSearch.isEmpty else { return n }
        return n.filter { $0.name.localizedCaseInsensitiveContains(personSearch) }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Sortierung") {
                    Picker("Sortieren", selection: $sort) {
                        ForEach(sorts, id: \.0) { Text($0.1).tag($0.0) }
                    }.pickerStyle(.inline).labelsHidden()
                }
                Section("Medientyp") {
                    Picker("Typ", selection: Binding(get: { mediaType ?? "" },
                                                     set: { mediaType = $0.isEmpty ? nil : $0 })) {
                        ForEach(media, id: \.1) { Text($0.1).tag($0.0 ?? "") }
                    }.pickerStyle(.segmented)
                }
                Section("Person") {
                    if let pid = personId {
                        HStack {
                            Label(personName ?? "Person #\(pid)", systemImage: "person.fill")
                            Spacer()
                            Button("Entfernen") { personId = nil; personName = nil }.foregroundStyle(.red)
                        }
                    } else {
                        TextField("Person suchen…", text: $personSearch)
                        ForEach(namedPeople.prefix(personSearch.isEmpty ? 8 : 30)) { p in
                            Button {
                                personId = p.id; personName = p.name; personSearch = ""
                            } label: { Label(p.name, systemImage: "person").foregroundStyle(.primary) }
                        }
                    }
                }
                Section {
                    Button("Filter zurücksetzen") {
                        sort = "newest"; mediaType = nil; personId = nil; personName = nil
                    }.foregroundStyle(.red)
                }
            }
            .navigationTitle("Filter & Sortierung")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Anwenden") { onApply(); dismiss() }.bold()
                }
            }
            .task { if people.isEmpty { people = (try? await api.people()) ?? [] } }
        }
    }
}
