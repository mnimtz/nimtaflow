import SwiftUI

/// People + their relationships. Tap a person to see/manage connections and add new ones.
struct RelationshipsView: View {
    @EnvironmentObject var api: APIClient
    @State private var graph: RelGraph?
    @State private var selected: RelNode?

    var body: some View {
        NavigationStack {
            List {
                Section("Personen") {
                    ForEach(graph?.nodes ?? []) { n in
                        Button { selected = n } label: {
                            HStack {
                                Avatar(url: api.url("api/people/\(n.id)/avatar"), initials: n.name.firstInitial, size: 36)
                                Text(n.name)
                                Spacer()
                                Text("\(edgeCount(n.id))").foregroundStyle(.secondary).font(.caption)
                                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
                            }
                        }.foregroundStyle(.primary)
                    }
                }
            }
            .navigationTitle("Beziehungen")
            .task { graph = try? await api.relationshipsGraph() }
            .refreshable { graph = try? await api.relationshipsGraph() }
            .sheet(item: $selected) { n in
                PersonRelSheet(node: n, allNodes: graph?.nodes ?? []) { Task { graph = try? await api.relationshipsGraph() } }
            }
        }
    }
    func edgeCount(_ id: Int) -> Int { (graph?.edges ?? []).filter { $0.from == id || $0.to == id }.count }
}

struct PersonRelSheet: View {
    @EnvironmentObject var api: APIClient
    let node: RelNode
    let allNodes: [RelNode]
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
                        ForEach(allNodes.filter { $0.id != node.id }) { Text($0.name).tag(Int?.some($0.id)) }
                    }
                    Button("Verbindung anlegen") {
                        if let o = addOther { Task { try? await api.addRelationship(from: node.id, to: o, type: addType); await reload(); onChange() } }
                    }.disabled(addOther == nil)
                }
            }
            .navigationTitle(node.name).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Fertig") { dismiss() } } }
            .task { await reload() }
        }
    }
    func reload() async { rels = (try? await api.personRelationships(node.id)) ?? []; onChange() }
}
