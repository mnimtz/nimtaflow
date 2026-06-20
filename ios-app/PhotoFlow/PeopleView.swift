import SwiftUI

struct PeopleView: View {
    @EnvironmentObject var api: APIClient
    @State private var people: [PersonV1] = []
    @State private var mergeMode = false
    @State private var selection: Set<Int> = []
    @State private var showMergeSheet = false
    @State private var error: String?
    @AppStorage("people_filter") private var filter = "named"

    let cols = [GridItem(.adaptive(minimum: 100), spacing: 16)]

    private func isNamed(_ p: PersonV1) -> Bool { !p.name.isEmpty && p.name != "Unbekannt" }
    private var filtered: [PersonV1] {
        switch filter {
        case "named":   return people.filter { isNamed($0) }
        case "unknown": return people.filter { !isNamed($0) && $0.face_count > 1 }
        case "single":  return people.filter { $0.face_count == 1 }
        default:        return people   // "all"
        }
    }
    private let filters: [(String, String)] = [
        ("named", "Erkannte Personen"), ("unknown", "Unbekannte Personen"),
        ("single", "Einzelgesichter"), ("all", "Alle"),
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVGrid(columns: cols, spacing: 16) {
                    ForEach(filtered) { p in
                        let cell = VStack(spacing: 6) {
                            Avatar(url: api.url(p.avatar_url), initials: p.name.firstInitial, size: 72)
                                .overlay {
                                    if mergeMode && selection.contains(p.id) {
                                        Circle().stroke(Color.indigo, lineWidth: 3)
                                    }
                                }
                            Text(p.name).font(.caption).lineLimit(1)
                            Text("\(p.face_count)").font(.caption2).foregroundStyle(.secondary)
                        }
                        if mergeMode {
                            cell.contentShape(Rectangle()).onTapGesture { toggle(p.id) }
                        } else {
                            NavigationLink(value: p) { cell }.buttonStyle(.plain)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Personen")
            .navigationDestination(for: PersonV1.self) { p in PersonDetailView(person: p) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Menu {
                        Picker("Filter", selection: $filter) {
                            ForEach(filters, id: \.0) { Text($0.1).tag($0.0) }
                        }
                    } label: {
                        Label(filters.first { $0.0 == filter }?.1 ?? "Filter",
                              systemImage: "line.3.horizontal.decrease.circle")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(mergeMode ? "Abbrechen" : "Zusammenführen") {
                        mergeMode.toggle(); if !mergeMode { selection.removeAll() }
                    }
                }
            }
            .overlay(alignment: .bottom) {
                if mergeMode {
                    HStack(spacing: 12) {
                        Text(selection.count < 2 ? "Mind. 2 Personen wählen" : "\(selection.count) gewählt")
                            .font(.callout)
                        if selection.count >= 2 {
                            Button("Weiter") { showMergeSheet = true }.buttonStyle(.borderedProminent)
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .background(.ultraThinMaterial, in: Capsule()).padding(.bottom, 8)
                }
            }
            .sheet(isPresented: $showMergeSheet) {
                MergeConfirmSheet(candidates: people.filter { selection.contains($0.id) }) { targetId in
                    Task { await merge(target: targetId); mergeMode = false; selection.removeAll() }
                }
            }
            .task { await load() }
            .refreshable { await load() }
            .alert("Fehler", isPresented: .constant(error != nil)) { Button("OK") { error = nil } } message: { Text(error ?? "") }
        }
    }

    func toggle(_ id: Int) { if selection.contains(id) { selection.remove(id) } else { selection.insert(id) } }
    func load() async { do { people = try await api.people() } catch { self.error = "Laden fehlgeschlagen" } }
    func merge(target: Int) async {
        let sources = Array(selection).filter { $0 != target }
        guard !sources.isEmpty else { return }
        do { try await api.mergePeople(target: target, sources: sources); await load() }
        catch { self.error = "Zusammenführen fehlgeschlagen" }
    }
}

/// Pick which person to KEEP when merging — the others fold into it (their photos
/// move over, then they're removed). Defaults to the one with the most faces.
struct MergeConfirmSheet: View {
    @EnvironmentObject var api: APIClient
    let candidates: [PersonV1]
    let onMerge: (Int) -> Void
    @Environment(\.dismiss) var dismiss
    @State private var targetId: Int?

    var body: some View {
        NavigationStack {
            List {
                Section("Behalten (Ziel)") {
                    ForEach(candidates) { p in
                        Button {
                            targetId = p.id
                        } label: {
                            HStack {
                                Avatar(url: api.url(p.avatar_url), initials: p.name.firstInitial, size: 40)
                                VStack(alignment: .leading) {
                                    Text(p.name.isEmpty ? "Unbekannt" : p.name)
                                    Text("\(p.face_count) Gesichter").font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: targetId == p.id ? "largecircle.fill.circle" : "circle")
                                    .foregroundStyle(targetId == p.id ? .indigo : .secondary)
                            }
                        }.foregroundStyle(.primary)
                    }
                }
                Section {
                    Text("Die übrigen \(max(0, candidates.count - 1)) Person(en) werden in die gewählte zusammengeführt (Fotos wandern mit, danach werden sie entfernt).")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Zusammenführen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Abbrechen") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Zusammenführen") { if let t = targetId { onMerge(t); dismiss() } }
                        .bold().disabled(targetId == nil)
                }
            }
            .onAppear { targetId = candidates.max { $0.face_count < $1.face_count }?.id }
        }
    }
}

struct PersonDetailView: View {
    @EnvironmentObject var api: APIClient
    let person: PersonV1
    @State private var photos: [PhotoV1] = []
    @State private var cursor: Int? = nil
    @State private var hasMore = true
    @State private var rels: [PersonRel] = []
    @State private var renaming = false
    @State private var newName = ""
    @State private var selected: PhotoV1?
    @Environment(\.dismiss) private var dismiss

    let cols = [GridItem(.adaptive(minimum: 90), spacing: 2)]

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                Avatar(url: api.url(person.avatar_url), initials: person.name.firstInitial, size: 96)
                Text(person.name).font(.title2.bold())
                Text("\(person.face_count) Fotos").foregroundStyle(.secondary)

                HStack {
                    Button { newName = person.name; renaming = true } label: { Label("Umbenennen", systemImage: "pencil") }
                        .buttonStyle(.bordered)
                    Button(role: .destructive) {
                        Task { try? await api.hidePerson(person.id, hidden: true); dismiss() }
                    } label: { Label("Ausblenden", systemImage: "eye.slash") }
                        .buttonStyle(.bordered)
                }

                if !rels.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("BEZIEHUNGEN").font(.caption.bold()).foregroundStyle(.secondary)
                        ForEach(rels) { r in
                            HStack {
                                Circle().fill(catColor(r.category)).frame(width: 8, height: 8)
                                Text(r.label).font(.caption).foregroundStyle(.secondary)
                                Text(r.other_name).font(.subheadline)
                                Spacer()
                            }
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal)
                }

                LazyVGrid(columns: cols, spacing: 2) {
                    ForEach(photos) { p in
                        Color.clear
                            .aspectRatio(1, contentMode: .fit)
                            .overlay { Thumb(url: api.url(p.thumb_medium_url)) }
                            .clipped()
                            .contentShape(Rectangle())
                            .onTapGesture { selected = p }
                            .onAppear { if p.id == photos.last?.id { Task { await loadPhotos() } } }
                    }
                }.padding(2)
            }
        }
        .navigationTitle(person.name).navigationBarTitleDisplayMode(.inline)
        .task { await loadPhotos(); rels = (try? await api.personRelationships(person.id)) ?? [] }
        .fullScreenCover(item: $selected) { p in PhotoPager(photos: photos, start: p) }
        .alert("Umbenennen", isPresented: $renaming) {
            TextField("Name", text: $newName)
            Button("Speichern") { Task { try? await api.renamePerson(person.id, name: newName) } }
            Button("Abbrechen", role: .cancel) {}
        }
    }
    func loadPhotos() async {
        guard hasMore else { return }
        do { let pg = try await api.personPhotos(person.id, cursor: cursor); photos += pg.items; cursor = pg.next_cursor; hasMore = pg.has_more }
        catch { hasMore = false }
    }
}

func catColor(_ c: String) -> Color { c == "family" ? .green : (c == "social" ? .blue : .gray) }
