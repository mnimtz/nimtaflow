import SwiftUI

/// All named people + their relationships. Tap a person to see/manage and add
/// connections. Lists EVERY named person (not only those already linked), so you
/// can actually create the first relationships.
struct RelationshipsView: View {
    @EnvironmentObject var api: APIClient
    @State private var people: [PersonV1] = []
    @State private var graph: RelGraph?
    @State private var selected: PersonV1?
    @State private var loading = false

    private var named: [PersonV1] { people.filter { !$0.name.isEmpty && $0.name != "Unbekannt" } }

    var body: some View {
        NavigationStack {
            List {
                if named.isEmpty && !loading {
                    ContentUnavailableView("Keine benannten Personen", systemImage: "person.2",
                        description: Text("Benenne erst Personen, dann kannst du hier Beziehungen anlegen."))
                }
                if !named.isEmpty {
                    Section("Personen") {
                        ForEach(named) { p in
                            Button { selected = p } label: {
                                HStack {
                                    Avatar(url: api.url("api/people/\(p.id)/avatar"), initials: p.name.firstInitial, size: 36)
                                    Text(p.name)
                                    Spacer()
                                    let c = edgeCount(p.id)
                                    if c > 0 { Text("\(c)").foregroundStyle(.secondary).font(.caption) }
                                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
                                }
                            }.foregroundStyle(.primary)
                        }
                    }
                }
            }
            .navigationTitle("Beziehungen")
            .task { await loadAll() }
            .refreshable { await loadAll() }
            .sheet(item: $selected) { p in
                PersonRelSheet(personId: p.id, personName: p.name,
                               candidates: named.filter { $0.id != p.id }.map { ($0.id, $0.name) }) {
                    Task { graph = try? await api.relationshipsGraph() }
                }
            }
        }
    }

    func loadAll() async {
        loading = true; defer { loading = false }
        async let ppl = api.people()
        async let g = api.relationshipsGraph()
        people = (try? await ppl) ?? []
        graph = try? await g
    }
    func edgeCount(_ id: Int) -> Int { (graph?.edges ?? []).filter { $0.from == id || $0.to == id }.count }
}

struct PersonRelSheet: View {
    @EnvironmentObject var api: APIClient
    let personId: Int
    let personName: String
    let candidates: [(Int, String)]
    let onChange: () -> Void
    @Environment(\.dismiss) var dismiss
    @State private var rels: [PersonRel] = []
    @State private var addType = "parent"
    @State private var addOther: Int?

    let types: [(String, String)] = [("parent","Elternteil von"),("grandparent","Großelternteil von"),("partner","Partner"),("sibling","Geschwister"),("relative","Verwandt"),("friend","Freund/in"),("colleague","Kollege/in"),("other","Verbindung")]

    var body: some View {
        NavigationStack {
            List {
                Section("Verbindungen") {
                    if rels.isEmpty { Text("Noch keine.").foregroundStyle(.secondary) }
                    ForEach(rels) { r in
                        HStack {
                            Circle().fill(catColor(r.category)).frame(width: 8, height: 8)
                            Text(r.label).font(.caption).foregroundStyle(.secondary)
                            Text(r.other_name)
                        }
                        .swipeActions { Button("Löschen", role: .destructive) { Task { try? await api.deleteRelationship(r.id); await reload() } } }
                    }
                }
                Section("Hinzufügen") {
                    Picker("Beziehung", selection: $addType) { ForEach(types, id: \.0) { Text($0.1).tag($0.0) } }
                    Picker("Person", selection: $addOther) {
                        Text("— wählen —").tag(Int?.none)
                        ForEach(candidates, id: \.0) { Text($0.1).tag(Int?.some($0.0)) }
                    }
                    Button("Verbindung anlegen") {
                        if let o = addOther { Task { try? await api.addRelationship(from: personId, to: o, type: addType); await reload(); onChange() } }
                    }.disabled(addOther == nil)
                }
            }
            .navigationTitle(personName).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Fertig") { dismiss() } } }
            .task { await reload() }
        }
    }
    func reload() async { rels = (try? await api.personRelationships(personId)) ?? []; onChange() }
}
