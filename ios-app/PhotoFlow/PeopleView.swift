import SwiftUI

struct PeopleView: View {
    @EnvironmentObject var api: APIClient
    var initialPersonId: Int? = nil          // Deep-Select vom Assistenten ("öffne Anjas Seite")
    @State private var navPath: [PersonV1] = []
    @State private var deepLinkApplied = false
    @State private var people: [PersonV1] = []
    @State private var mergeMode = false
    @State private var selection: Set<Int> = []
    @State private var showMergeSheet = false
    @State private var showSuggestions = false
    @State private var error: String?
    @AppStorage("people_filter") private var filter = "named"
    @AppStorage("people_sort") private var sortMode = "count"   // "count" (Default) | "name"

    let cols = [GridItem(.adaptive(minimum: 100), spacing: 16)]

    private func isNamed(_ p: PersonV1) -> Bool { !p.name.isEmpty && p.name != "Unbekannt" }
    private func count(_ p: PersonV1) -> Int { p.photo_count > 0 ? p.photo_count : p.face_count }
    private func sorted(_ list: [PersonV1]) -> [PersonV1] {
        if sortMode == "name" {
            return list.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        }
        return list.sorted { count($0) != count($1) ? count($0) > count($1)
                             : $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }
    private var namedPeople: [PersonV1] { sorted(people.filter { isNamed($0) }) }
    private var unknownPeople: [PersonV1] { sorted(people.filter { !isNamed($0) }) }
    private let sorts: [(String, String)] = [("count", "Nach Anzahl"), ("name", "Nach Name")]

    @ViewBuilder
    private func personCell(_ p: PersonV1) -> some View {
        VStack(spacing: 6) {
            Avatar(url: api.url(p.avatar_url), initials: p.name.firstInitial, size: 72)
                .overlay {
                    if mergeMode && selection.contains(p.id) {
                        Circle().stroke(Color.indigo, lineWidth: 3)
                    }
                }
            Text(p.name.isEmpty ? "Unbekannt" : p.name).font(.caption).lineLimit(1)
            Text("\(p.photo_count > 0 ? p.photo_count : p.face_count) Fotos")
                .font(.caption2).foregroundStyle(.secondary)
        }
    }

    var body: some View {
        NavigationStack(path: $navPath) {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    // ── Benannte Personen ────────────────────────────────────
                    if !namedPeople.isEmpty {
                        LazyVGrid(columns: cols, spacing: 16) {
                            ForEach(namedPeople) { p in
                                if mergeMode {
                                    personCell(p).contentShape(Rectangle()).onTapGesture { toggle(p.id) }
                                } else {
                                    NavigationLink(value: p) { personCell(p) }.buttonStyle(.plain)
                                }
                            }
                        }
                        .padding()
                    }

                    // ── Unbekannte Personen ──────────────────────────────────
                    if !unknownPeople.isEmpty {
                        VStack(alignment: .leading, spacing: 0) {
                            HStack {
                                Text("Unbekannte Personen")
                                    .font(.subheadline.bold())
                                    .foregroundStyle(.secondary)
                                Text("(\(unknownPeople.count))")
                                    .font(.subheadline)
                                    .foregroundStyle(.tertiary)
                            }
                            .padding(.horizontal)
                            .padding(.top, namedPeople.isEmpty ? 16 : 4)
                            .padding(.bottom, 12)

                            LazyVGrid(columns: cols, spacing: 16) {
                                ForEach(unknownPeople) { p in
                                    if mergeMode {
                                        personCell(p).contentShape(Rectangle()).onTapGesture { toggle(p.id) }
                                    } else {
                                        NavigationLink(value: p) { personCell(p) }.buttonStyle(.plain)
                                    }
                                }
                            }
                            .padding(.horizontal)
                            .padding(.bottom, 16)
                        }
                    }
                }
            }
            .navigationTitle("Personen")
            .navigationDestination(for: PersonV1.self) { p in PersonDetailView(person: p) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Menu {
                        Picker("Sortierung", selection: $sortMode) {
                            ForEach(sorts, id: \.0) { Text($0.1).tag($0.0) }
                        }
                    } label: {
                        Label("Sortierung", systemImage: "line.3.horizontal.decrease.circle")
                    }
                }
                // Zusammenführen + Vorschläge (Gesichts-Verwaltung) nur für Admins.
                if api.isAdmin {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button(mergeMode ? "Abbrechen" : "Zusammenführen") {
                            mergeMode.toggle(); if !mergeMode { selection.removeAll() }
                        }
                    }
                    if !mergeMode {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button { showSuggestions = true } label: { Image(systemName: "sparkles") }
                        }
                    }
                }
            }
            .sheet(isPresented: $showSuggestions) { SuggestionsView() }
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
    func load() async {
        do {
            people = try await api.people()
            // Deep-Select: direkt zur angefragten Person springen (statt nur die Liste).
            if !deepLinkApplied, let pid = initialPersonId, let p = people.first(where: { $0.id == pid }) {
                deepLinkApplied = true; navPath = [p]
            }
        } catch { self.error = "Laden fehlgeschlagen" }
    }
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
    @State private var displayName = ""   // reflects renames immediately (person is a let)
    @State private var meNote = false
    @State private var showDelete = false
    @State private var selected: PhotoV1?
    @State private var sort: GridSort = .newest
    @State private var mediaFilter: GridMediaFilter = .all
    @Environment(\.dismiss) private var dismiss

    let cols = [GridItem(.adaptive(minimum: 90), spacing: 2)]

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                Avatar(url: api.url(person.avatar_url), initials: (displayName.isEmpty ? person.name : displayName).firstInitial, size: 96)
                Text(displayName.isEmpty ? person.name : displayName).font(.title2.bold())
                Text("\(person.face_count) Fotos").foregroundStyle(.secondary)

                HStack {
                    Button { newName = displayName.isEmpty ? person.name : displayName; renaming = true } label: { Label("Umbenennen", systemImage: "pencil") }
                        .buttonStyle(.bordered)
                    Button {
                        Task { try? await api.setAsMe(person.id); meNote = true }
                    } label: { Label("Das bin ich", systemImage: "person.fill.checkmark") }
                        .buttonStyle(.bordered)
                    Menu {
                        Button { Task { try? await api.hidePerson(person.id, hidden: true); dismiss() } } label: {
                            Label("Ausblenden", systemImage: "eye.slash")
                        }
                        Button(role: .destructive) { showDelete = true } label: {
                            Label("Person löschen", systemImage: "trash")
                        }
                    } label: { Image(systemName: "ellipsis.circle").font(.title3) }
                }
                if meNote { Text("Als „ich“ verknüpft – die KI weiß jetzt, wer du bist.").font(.caption).foregroundStyle(.green) }

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

                HStack(spacing: 8) {
                    Menu {
                        Picker("Sortierung", selection: $sort) {
                            ForEach(GridSort.allCases) { Text($0.label).tag($0) }
                        }
                    } label: {
                        Label(sort.label, systemImage: "arrow.up.arrow.down").font(.subheadline)
                    }
                    Menu {
                        Picker("Medientyp", selection: $mediaFilter) {
                            ForEach(GridMediaFilter.allCases) { Text($0.label).tag($0) }
                        }
                    } label: {
                        Label(mediaFilter.label, systemImage: "line.3.horizontal.decrease.circle").font(.subheadline)
                    }
                    Spacer()
                }
                .padding(.horizontal, 8)
                .onChange(of: sort) { _, _ in Task { await reloadPhotos() } }
                .onChange(of: mediaFilter) { _, _ in Task { await reloadPhotos() } }

                LazyVGrid(columns: cols, spacing: 2) {
                    ForEach(photos) { p in
                        PhotoTile(photo: p)
                            .onTapGesture { selected = p }
                            .onAppear { if p.id == photos.last?.id { Task { await loadPhotos() } } }
                    }
                }.padding(2)
            }
        }
        .navigationTitle(displayName.isEmpty ? person.name : displayName).navigationBarTitleDisplayMode(.inline)
        .task {
            if displayName.isEmpty { displayName = person.name }
            await loadPhotos(); rels = (try? await api.personRelationships(person.id)) ?? []
        }
        .fullScreenCover(item: $selected) { p in
            PhotoPager(photos: photos, start: p, onRemoved: { id in photos.removeAll { $0.id == id } })
        }
        .confirmationDialog("Diese Person löschen? Die Fotos bleiben erhalten, nur die Personen-Zuordnung wird entfernt.",
                            isPresented: $showDelete, titleVisibility: .visible) {
            Button("Person löschen", role: .destructive) {
                Task { try? await api.deletePerson(person.id); dismiss() }
            }
            Button("Abbrechen", role: .cancel) {}
        }
        .alert("Umbenennen", isPresented: $renaming) {
            TextField("Name", text: $newName)
            Button("Speichern") {
                let target = newName.trimmingCharacters(in: .whitespaces)
                guard !target.isEmpty else { return }
                Task {
                    // If the typed name already belongs to a DIFFERENT person, merge
                    // this one into it instead of creating a duplicate name.
                    let all = (try? await api.people()) ?? []
                    if let existing = all.first(where: {
                        $0.id != person.id &&
                        $0.name.compare(target, options: .caseInsensitive) == .orderedSame
                    }) {
                        do {
                            try await api.mergePeople(target: existing.id, sources: [person.id])
                            dismiss()
                        } catch { /* keep old name shown on failure */ }
                    } else {
                        do { try await api.renamePerson(person.id, name: target); displayName = target }
                        catch { /* keep old name shown on failure */ }
                    }
                }
            }
            Button("Abbrechen", role: .cancel) {}
        }
    }
    func loadPhotos() async {
        guard hasMore else { return }
        do {
            let pg = try await api.personPhotos(person.id, cursor: cursor,
                                                sort: sort.rawValue, mediaType: mediaFilter.mediaType)
            photos += pg.items; cursor = pg.next_cursor; hasMore = pg.has_more
        }
        catch { hasMore = false }
    }

    /// Sort/filter changed → restart the feed.
    func reloadPhotos() async {
        photos = []; cursor = nil; hasMore = true
        await loadPhotos()
    }
}

func catColor(_ c: String) -> Color { c == "family" ? .green : (c == "social" ? .blue : .gray) }

/// Borderline face→person suggestions: confirm/reject per face or per whole person.
struct SuggestionsView: View {
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss
    @State private var groups: [SuggestionGroup] = []
    @State private var loading = true
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Group {
                if loading {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if groups.isEmpty {
                    VStack(spacing: 8) {
                        Image(systemName: "sparkles").font(.largeTitle).foregroundStyle(.secondary)
                        Text("Keine offenen Vorschläge").foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List {
                        ForEach(groups) { g in
                            Section {
                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack(spacing: 10) {
                                        ForEach(g.faces) { f in
                                            FaceCropThumb(
                                                url: api.url("api/people/faces/\(f.id)/crop"),
                                                onConfirm: { Task { await act { try await api.confirmSuggestion(faceId: f.id) } } },
                                                onReject:  { Task { await act { try await api.rejectSuggestion(faceId: f.id) } } })
                                        }
                                    }.padding(.vertical, 4)
                                }
                                HStack {
                                    Button { Task { await act { try await api.confirmAllSuggestions(personId: g.person_id) } } } label: {
                                        Label("Alle bestätigen", systemImage: "checkmark.circle.fill")
                                    }.tint(.green)
                                    Spacer()
                                    Button(role: .destructive) { Task { await act { try await api.rejectAllSuggestions(personId: g.person_id) } } } label: {
                                        Label("Alle ablehnen", systemImage: "xmark.circle.fill")
                                    }
                                }.buttonStyle(.bordered).disabled(busy)
                            } header: {
                                Text("\(g.name) · \(g.count)×")
                            }
                        }
                    }
                }
            }
            .navigationTitle("Vorschläge")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button("Fertig") { dismiss() } } }
            .task { await load() }
            .refreshable { await load() }
        }
    }

    private func load() async {
        loading = true
        groups = (try? await api.faceSuggestions().groups) ?? []
        loading = false
    }
    private func act(_ op: () async throws -> Void) async {
        busy = true
        try? await op()
        await load()
        busy = false
    }
}

struct FaceCropThumb: View {
    let url: URL?
    var onConfirm: () -> Void
    var onReject: () -> Void
    var body: some View {
        VStack(spacing: 4) {
            // Authenticated loader — plain AsyncImage sends no Bearer header → 401 →
            // all suggestion crops were blank.
            Thumb(url: url)
                .frame(width: 72, height: 72).clipShape(RoundedRectangle(cornerRadius: 10))
            HStack(spacing: 14) {
                Button(action: onConfirm) { Image(systemName: "checkmark.circle.fill").foregroundStyle(.green) }
                Button(action: onReject) { Image(systemName: "xmark.circle.fill").foregroundStyle(.red) }
            }.font(.title3).buttonStyle(.plain)
        }
    }
}
