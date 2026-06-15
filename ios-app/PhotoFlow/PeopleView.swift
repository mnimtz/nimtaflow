import SwiftUI

struct PeopleView: View {
    @EnvironmentObject var api: APIClient
    @State private var people: [PersonV1] = []
    @State private var mergeMode = false
    @State private var selection: Set<Int> = []
    @State private var error: String?

    let cols = [GridItem(.adaptive(minimum: 100), spacing: 16)]

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVGrid(columns: cols, spacing: 16) {
                    ForEach(people) { p in
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
                ToolbarItem(placement: .topBarTrailing) {
                    Button(mergeMode ? "Fertig" : "Auswählen") {
                        if mergeMode && selection.count >= 2 { Task { await merge() } }
                        mergeMode.toggle(); if !mergeMode { selection.removeAll() }
                    }
                }
            }
            .overlay(alignment: .bottom) {
                if mergeMode && selection.count >= 2 {
                    Text("\(selection.count) ausgewählt — „Fertig" führt zusammen")
                        .font(.caption).padding(8).background(.ultraThinMaterial, in: Capsule()).padding(.bottom)
                }
            }
            .task { await load() }
            .refreshable { await load() }
            .alert("Fehler", isPresented: .constant(error != nil)) { Button("OK") { error = nil } } message: { Text(error ?? "") }
        }
    }

    func toggle(_ id: Int) { if selection.contains(id) { selection.remove(id) } else { selection.insert(id) } }
    func load() async { do { people = try await api.people() } catch { self.error = "Laden fehlgeschlagen" } }
    func merge() async {
        let ids = Array(selection)
        guard let target = ids.first else { return }
        do { try await api.mergePeople(target: target, sources: Array(ids.dropFirst())); selection.removeAll(); await load() }
        catch { self.error = "Zusammenführen fehlgeschlagen" }
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
                        Thumb(url: api.url(p.thumb_medium_url)).aspectRatio(1, contentMode: .fill).frame(minHeight: 90)
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
