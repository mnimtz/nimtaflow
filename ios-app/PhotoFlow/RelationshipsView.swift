import SwiftUI

/// Visual relationship map. Nodes (people) are laid out with a light force
/// simulation over a few iterations, edges drawn between them (coloured by
/// category). Pan/zoom to explore; tap a node to open that person / their
/// relations; "+" adds a new relationship. A flat list of all named people
/// stays available as a fallback / quick entry point.
struct RelationshipsView: View {
    @EnvironmentObject var api: APIClient
    @State private var people: [PersonV1] = []
    @State private var graph: RelGraph?
    @State private var selected: PersonV1?
    @State private var tappedNode: RelNode?
    @State private var loading = false
    @State private var showAdd = false
    @State private var showList = false

    private var named: [PersonV1] { people.filter { !$0.name.isEmpty && $0.name != "Unbekannt" } }

    var body: some View {
        NavigationStack {
            Group {
                if let g = graph, !g.nodes.isEmpty {
                    RelGraphCanvas(graph: g) { node in tappedNode = node }
                } else if loading {
                    ProgressView()
                } else {
                    ContentUnavailableView("Keine Beziehungen", systemImage: "point.3.connected.trianglepath.dotted",
                        description: Text("Benenne Personen und lege über „+“ Verbindungen an."))
                }
            }
            .navigationTitle("Beziehungen")
            .task { await loadAll() }
            .refreshable { await loadAll() }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showList = true } label: { Image(systemName: "list.bullet") }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showAdd = true } label: { Image(systemName: "plus") }
                        .disabled(named.count < 2)
                }
            }
            // Tap a node → small sheet to view/manage that person's relations.
            .sheet(item: $tappedNode) { node in
                PersonRelSheet(personId: node.id, personName: node.name,
                               candidates: named.filter { $0.id != node.id }.map { ($0.id, $0.name) }) {
                    Task { graph = try? await api.relationshipsGraph() }
                }
            }
            // Quick list of all named people (also lets you create first links).
            .sheet(isPresented: $showList) {
                RelPeopleListSheet(people: named, graph: graph) { p in
                    showList = false; selected = p
                }
            }
            .sheet(item: $selected) { p in
                PersonRelSheet(personId: p.id, personName: p.name,
                               candidates: named.filter { $0.id != p.id }.map { ($0.id, $0.name) }) {
                    Task { graph = try? await api.relationshipsGraph() }
                }
            }
            .sheet(isPresented: $showAdd) {
                AddRelationshipSheet(candidates: named.map { ($0.id, $0.name) }) {
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
}

// MARK: - Graph canvas (positioned avatars + connecting lines + pan/zoom)

private struct RelGraphCanvas: View {
    @EnvironmentObject var api: APIClient
    let graph: RelGraph
    let onTap: (RelNode) -> Void

    @State private var positions: [Int: CGPoint] = [:]   // node id → unit position (0…1)
    @State private var scale: CGFloat = 1
    @State private var lastScale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero

    var body: some View {
        GeometryReader { geo in
            let size = geo.size
            ZStack {
                // Edges
                Canvas { ctx, _ in
                    for e in graph.edges {
                        guard let a = positions[e.from], let b = positions[e.to] else { continue }
                        let pa = point(a, in: size); let pb = point(b, in: size)
                        var path = Path(); path.move(to: pa); path.addLine(to: pb)
                        ctx.stroke(path, with: .color(catColor(e.category).opacity(0.55)),
                                   lineWidth: 2)
                    }
                }
                // Nodes
                ForEach(graph.nodes) { node in
                    if let u = positions[node.id] {
                        let p = point(u, in: size)
                        Button { onTap(node) } label: {
                            VStack(spacing: 3) {
                                Avatar(url: api.url("api/people/\(node.id)/avatar"),
                                       initials: node.name.firstInitial, size: 46)
                                    .overlay(Circle().stroke(Color(.systemBackground), lineWidth: 2))
                                Text(node.name).font(.caption2).lineLimit(1)
                                    .padding(.horizontal, 4)
                                    .background(Color(.systemBackground).opacity(0.7))
                                    .foregroundStyle(.primary)
                            }
                        }
                        .buttonStyle(.plain)
                        .position(p)
                    }
                }
            }
            .frame(width: size.width, height: size.height)
            .scaleEffect(scale)
            .offset(offset)
            .contentShape(Rectangle())
            .gesture(
                SimultaneousGesture(
                    MagnificationGesture()
                        .onChanged { v in scale = min(max(lastScale * v, 0.4), 4) }
                        .onEnded { _ in lastScale = scale },
                    DragGesture()
                        .onChanged { v in
                            offset = CGSize(width: lastOffset.width + v.translation.width,
                                            height: lastOffset.height + v.translation.height)
                        }
                        .onEnded { _ in lastOffset = offset }
                )
            )
            .onTapGesture(count: 2) {
                withAnimation(.spring) {
                    scale = 1; lastScale = 1; offset = .zero; lastOffset = .zero
                }
            }
            .onAppear { if positions.isEmpty { layout() } }
            .onChange(of: graph.nodes.count) { _, _ in layout() }
        }
    }

    private func point(_ unit: CGPoint, in size: CGSize) -> CGPoint {
        let pad: CGFloat = 60
        return CGPoint(x: pad + unit.x * (size.width - 2 * pad),
                       y: pad + unit.y * (size.height - 2 * pad))
    }

    /// Seed nodes on a circle, then run a few force-simulation iterations
    /// (repulsion between all nodes + spring along edges). Output normalised
    /// back into the 0…1 unit square.
    private func layout() {
        let nodes = graph.nodes
        guard !nodes.isEmpty else { positions = [:]; return }
        let n = nodes.count
        var pos: [Int: CGPoint] = [:]
        for (i, node) in nodes.enumerated() {
            let a = Double(i) / Double(n) * 2 * .pi
            pos[node.id] = CGPoint(x: 0.5 + 0.4 * cos(a), y: 0.5 + 0.4 * sin(a))
        }
        if n > 1 {
            let ids = nodes.map { $0.id }
            let kRep = 0.020, kSpring = 0.08, ideal = 0.30
            for _ in 0..<120 {
                var disp: [Int: CGVector] = [:]
                for id in ids { disp[id] = .zero }
                // Repulsion
                for i in 0..<n {
                    for j in (i+1)..<n {
                        let a = ids[i], b = ids[j]
                        var dx = pos[a]!.x - pos[b]!.x
                        var dy = pos[a]!.y - pos[b]!.y
                        var d = (dx*dx + dy*dy).squareRoot()
                        if d < 0.0001 { d = 0.0001; dx = 0.001; dy = 0.001 }
                        let f = kRep / (d * d)
                        disp[a]! .dx += dx / d * f; disp[a]!.dy += dy / d * f
                        disp[b]! .dx -= dx / d * f; disp[b]!.dy -= dy / d * f
                    }
                }
                // Springs along edges
                for e in graph.edges {
                    guard let pa = pos[e.from], let pb = pos[e.to] else { continue }
                    let dx = pb.x - pa.x, dy = pb.y - pa.y
                    let d = max((dx*dx + dy*dy).squareRoot(), 0.0001)
                    let f = kSpring * (d - ideal)
                    let fx = dx / d * f, fy = dy / d * f
                    disp[e.from]?.dx += fx; disp[e.from]?.dy += fy
                    disp[e.to]?.dx -= fx; disp[e.to]?.dy -= fy
                }
                for id in ids {
                    var p = pos[id]!
                    p.x = min(max(p.x + disp[id]!.dx, 0), 1)
                    p.y = min(max(p.y + disp[id]!.dy, 0), 1)
                    pos[id] = p
                }
            }
            // Re-normalise to fill the unit square nicely.
            let xs = pos.values.map { $0.x }, ys = pos.values.map { $0.y }
            let minX = xs.min()!, maxX = xs.max()!, minY = ys.min()!, maxY = ys.max()!
            let spanX = max(maxX - minX, 0.0001), spanY = max(maxY - minY, 0.0001)
            for id in ids {
                let p = pos[id]!
                pos[id] = CGPoint(x: (p.x - minX) / spanX, y: (p.y - minY) / spanY)
            }
        }
        positions = pos
    }
}

// MARK: - Add relationship (standalone, pick both people)

private struct AddRelationshipSheet: View {
    @EnvironmentObject var api: APIClient
    let candidates: [(Int, String)]
    let onChange: () -> Void
    @Environment(\.dismiss) var dismiss

    @State private var from: Int?
    @State private var to: Int?
    @State private var type = "parent"
    @State private var busy = false

    private let types: [(String, String)] = [("parent","Elternteil von"),("grandparent","Großelternteil von"),("partner","Partner"),("sibling","Geschwister"),("relative","Verwandt"),("friend","Freund/in"),("colleague","Kollege/in"),("other","Verbindung")]

    var body: some View {
        NavigationStack {
            Form {
                Section("Personen") {
                    Picker("Von", selection: $from) {
                        Text("— wählen —").tag(Int?.none)
                        ForEach(candidates, id: \.0) { Text($0.1).tag(Int?.some($0.0)) }
                    }
                    Picker("Zu", selection: $to) {
                        Text("— wählen —").tag(Int?.none)
                        ForEach(candidates.filter { $0.0 != from }, id: \.0) { Text($0.1).tag(Int?.some($0.0)) }
                    }
                }
                Section("Beziehung") {
                    Picker("Art", selection: $type) { ForEach(types, id: \.0) { Text($0.1).tag($0.0) } }
                }
                Section {
                    Button {
                        guard let f = from, let t = to else { return }
                        Task {
                            busy = true; defer { busy = false }
                            try? await api.addRelationship(from: f, to: t, type: type)
                            onChange(); dismiss()
                        }
                    } label: {
                        HStack { if busy { ProgressView() }; Text("Verbindung anlegen") }
                    }.disabled(from == nil || to == nil || from == to || busy)
                }
            }
            .navigationTitle("Neue Beziehung")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Schließen") { dismiss() } } }
        }
    }
}

// MARK: - Fallback people list

private struct RelPeopleListSheet: View {
    @EnvironmentObject var api: APIClient
    let people: [PersonV1]
    let graph: RelGraph?
    let onPick: (PersonV1) -> Void
    @Environment(\.dismiss) var dismiss

    private func edgeCount(_ id: Int) -> Int {
        (graph?.edges ?? []).filter { $0.from == id || $0.to == id }.count
    }

    var body: some View {
        NavigationStack {
            List {
                if people.isEmpty {
                    ContentUnavailableView("Keine benannten Personen", systemImage: "person.2",
                        description: Text("Benenne erst Personen, dann kannst du hier Beziehungen anlegen."))
                }
                ForEach(people) { p in
                    Button { onPick(p) } label: {
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
            .navigationTitle("Personen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Fertig") { dismiss() } } }
        }
    }
}

// MARK: - Per-person relations sheet (unchanged behaviour)

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
