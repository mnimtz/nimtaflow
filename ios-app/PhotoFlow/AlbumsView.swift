import SwiftUI

/// Browse albums (manual / smart / AI) and open one into a photo grid.
/// Reuses the same `Thumb` + `PhotoPager` the gallery uses, so an album opens
/// into the identical swipeable full-screen viewer.
struct AlbumsView: View {
    @EnvironmentObject var api: APIClient
    @State private var albums: [AlbumV1] = []
    @State private var loading = false
    @State private var error: String?
    @State private var showCreate = false

    let cols = [GridItem(.adaptive(minimum: 150), spacing: 12)]

    var body: some View {
        NavigationStack {
            ScrollView {
                // Only when there's nothing to show — a failed refresh over loaded
                // albums shouldn't slap an error over good data.
                if let error, albums.isEmpty { Text(error).foregroundStyle(.secondary).padding() }
                LazyVGrid(columns: cols, spacing: 14) {
                    ForEach(albums) { a in
                        NavigationLink(value: a) { AlbumCard(album: a) }
                            .buttonStyle(.plain)
                    }
                }
                .padding(12)
                if loading { ProgressView().padding() }
                if !loading && albums.isEmpty && error == nil {
                    ContentUnavailableView("Keine Alben", systemImage: "rectangle.stack",
                                           description: Text("Alben aus dem Web erscheinen hier automatisch."))
                        .padding(.top, 60)
                }
            }
            .navigationTitle("Alben")
            .navigationDestination(for: AlbumV1.self) { a in
                AlbumDetailView(album: a) { Task { await load() } }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showCreate = true } label: { Image(systemName: "plus") }
                }
            }
            .sheet(isPresented: $showCreate) {
                CreateAlbumSheet { await load() }
                    .presentationDetents([.medium, .large])
            }
            .refreshable { await load() }
            .task { if albums.isEmpty { await load() } }
        }
    }

    func load() async {
        loading = true; defer { loading = false }
        do { albums = try await api.albums(); error = nil }
        catch { self.error = "Alben konnten nicht geladen werden." }
    }
}

/// Create an album with a type: Normal (manual), Smart (by person) or KI
/// (freetext prompt). Calls api.createAlbum(name:type:smartCriteria:aiPrompt:).
private struct CreateAlbumSheet: View {
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss
    let onCreated: () async -> Void

    @State private var name = ""
    @State private var type = "manual"        // manual | smart | ai
    @State private var aiPrompt = ""
    @State private var people: [PersonV1] = []
    @State private var selectedPeople: Set<Int> = []
    @State private var requireAll = false
    @State private var busy = false

    private var canCreate: Bool {
        guard !name.trimmingCharacters(in: .whitespaces).isEmpty, !busy else { return false }
        switch type {
        case "smart": return !selectedPeople.isEmpty
        case "ai":    return !aiPrompt.trimmingCharacters(in: .whitespaces).isEmpty
        default:      return true
        }
    }

    private func isNamed(_ p: PersonV1) -> Bool { !p.name.isEmpty && p.name != "Unbekannt" }

    var body: some View {
        NavigationStack {
            Form {
                Section("Name") {
                    TextField("Album-Name", text: $name)
                }
                Section("Typ") {
                    Picker("Typ", selection: $type) {
                        Text("Normal").tag("manual")
                        Text("Smart").tag("smart")
                        Text("KI").tag("ai")
                    }
                    .pickerStyle(.segmented)
                    switch type {
                    case "manual": Text("Fotos später manuell hinzufügen.")
                                    .font(.caption).foregroundStyle(.secondary)
                    case "smart":  Text("Füllt sich automatisch mit Fotos der gewählten Personen.")
                                    .font(.caption).foregroundStyle(.secondary)
                    case "ai":     Text("Gemini wählt passende Fotos zur Beschreibung aus.")
                                    .font(.caption).foregroundStyle(.secondary)
                    default: EmptyView()
                    }
                }
                if type == "smart" {
                    Section("Personen") {
                        if selectedPeople.count > 1 {
                            Toggle("Müssen alle gemeinsam vorkommen", isOn: $requireAll)
                        }
                        ForEach(people.filter(isNamed)) { p in
                            Button {
                                if selectedPeople.contains(p.id) { selectedPeople.remove(p.id) }
                                else { selectedPeople.insert(p.id) }
                            } label: {
                                HStack {
                                    Avatar(url: api.url(p.avatar_url), initials: p.name.firstInitial, size: 32)
                                    Text(p.name).foregroundStyle(.primary)
                                    Spacer()
                                    if selectedPeople.contains(p.id) {
                                        Image(systemName: "checkmark.circle.fill").foregroundStyle(.indigo)
                                    }
                                }
                            }
                        }
                    }
                }
                if type == "ai" {
                    Section("Beschreibung") {
                        TextField("z. B. Sonnenuntergänge am Strand", text: $aiPrompt, axis: .vertical)
                            .lineLimit(2...5)
                    }
                }
                Section {
                    Button {
                        Task { await create() }
                    } label: {
                        HStack { if busy { ProgressView() }; Text("Erstellen") }
                    }.disabled(!canCreate)
                }
            }
            .navigationTitle("Neues Album")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Abbrechen") { dismiss() } } }
            .task { if people.isEmpty { people = (try? await api.people()) ?? [] } }
        }
    }

    func create() async {
        busy = true; defer { busy = false }
        let n = name.trimmingCharacters(in: .whitespaces)
        var smart: [String: Any]? = nil
        var prompt: String? = nil
        switch type {
        case "smart":
            var c: [String: Any] = ["person_ids": Array(selectedPeople)]
            if selectedPeople.count > 1 && requireAll { c["person_match"] = "all" }
            smart = c
        case "ai":
            prompt = aiPrompt.trimmingCharacters(in: .whitespaces)
        default: break
        }
        try? await api.createAlbum(name: n, type: type, smartCriteria: smart, aiPrompt: prompt)
        await onCreated()
        dismiss()
    }
}

private struct AlbumCard: View {
    @EnvironmentObject var api: APIClient
    let album: AlbumV1

    var typeIcon: String {
        switch album.album_type {
        case "smart": return "sparkles"
        case "ai": return "wand.and.stars"
        default: return "rectangle.stack.fill"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Color.clear
                .aspectRatio(1, contentMode: .fit)        // fixed square cell
                .overlay {
                    if let c = album.cover_url { Thumb(url: api.url(c)) }
                    else {
                        Color.gray.opacity(0.18)
                            .overlay(Image(systemName: "photo.stack").font(.largeTitle).foregroundStyle(.secondary))
                    }
                }
                .clipped()
                .overlay(alignment: .bottomLeading) {
                    Image(systemName: typeIcon)
                        .font(.caption).foregroundStyle(.white)
                        .padding(6).background(.black.opacity(0.45), in: Circle()).padding(8)
                }
                .clipShape(RoundedRectangle(cornerRadius: 14))
            Text(album.name).font(.subheadline.weight(.semibold)).lineLimit(1)
            Text("\(album.photo_count) Fotos").font(.caption).foregroundStyle(.secondary)
        }
    }
}

/// Photo grid for one album — paginated, opens the shared full-screen pager.
struct AlbumDetailView: View {
    @EnvironmentObject var api: APIClient
    let album: AlbumV1
    var onChange: () -> Void = {}
    @Environment(\.dismiss) private var dismiss
    @State private var photos: [PhotoV1] = []
    @State private var cursor: Int? = nil
    @State private var hasMore = true
    @State private var loading = false
    @State private var selected: PhotoV1?
    @State private var showShare = false
    @State private var showEdit = false
    @State private var displayName: String?
    @State private var displayType: String?
    @State private var sort: GridSort = .oldest   // Alben chronologisch: älteste zuerst → neu

    let cols = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        PhotoGridView(photos: photos,
                      onReachEnd: { Task { await load() } },
                      removeLabel: "Aus Album entfernen",
                      onRemove: { p in
                          Task { try? await api.removeFromAlbum(album.id, photoId: p.id)
                                 photos.removeAll { $0.id == p.id }; onChange() }
                      },
                      sort: $sort,
                      onControlsChange: { Task { await reload() } })
        .navigationTitle(displayName ?? album.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button { showShare = true } label: { Label("Teilen", systemImage: "square.and.arrow.up") }
                    Button { showEdit = true } label: { Label("Bearbeiten", systemImage: "pencil") }
                    if (displayType ?? album.album_type) != "manual" {
                        Button {
                            Task { try? await api.refreshAlbum(album.id); await reload(); onChange() }
                        } label: { Label("Aktualisieren", systemImage: "arrow.clockwise") }
                    }
                    Button(role: .destructive) {
                        Task { try? await api.deleteAlbum(album.id); onChange(); dismiss() }
                    } label: { Label("Album löschen", systemImage: "trash") }
                } label: { Image(systemName: "ellipsis.circle") }
            }
        }
        .task { if photos.isEmpty { await load() } }
        .sheet(isPresented: $showShare) {
            ShareSheetView(target: .album(id: album.id, title: displayName ?? album.name)).presentationDetents([.medium])
        }
        .sheet(isPresented: $showEdit) {
            AlbumEditSheet(album: album,
                           currentName: displayName ?? album.name,
                           currentType: displayType ?? album.album_type) { newName, newType in
                displayName = newName; displayType = newType
                await reload(); onChange()
            }
            .presentationDetents([.medium, .large])
        }
    }

    func load() async {
        guard hasMore, !loading else { return }
        loading = true; defer { loading = false }
        do {
            let page = try await api.albumPhotos(album.id, cursor: cursor, sort: sort.rawValue)
            photos += page.items; cursor = page.next_cursor; hasMore = page.has_more
        } catch { hasMore = false }
    }

    /// Sort changed → start the feed over with the new ordering.
    func reload() async {
        photos = []; cursor = nil; hasMore = true
        await load()
    }
}

/// Full album edit: rename, change type, and (for smart) pick the people whose
/// photos should fill it — no 1000-Limit, the server repopulates on save.
/// Mirrors the web AlbumEditModal for 1:1 parity.
private struct AlbumEditSheet: View {
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss
    let album: AlbumV1
    let currentName: String
    let currentType: String
    let onSaved: (_ name: String, _ type: String) async -> Void

    @State private var name = ""
    @State private var type = "manual"
    @State private var aiPrompt = ""
    @State private var people: [PersonV1] = []
    @State private var selectedPeople: Set<Int> = []
    @State private var requireAll = false
    @State private var busy = false

    private var canSave: Bool {
        guard !name.trimmingCharacters(in: .whitespaces).isEmpty, !busy else { return false }
        switch type {
        case "smart": return !selectedPeople.isEmpty
        case "ai":    return !aiPrompt.trimmingCharacters(in: .whitespaces).isEmpty
        default:      return true
        }
    }
    private func isNamed(_ p: PersonV1) -> Bool { !p.name.isEmpty && p.name != "Unbekannt" }

    var body: some View {
        NavigationStack {
            Form {
                Section("Name") { TextField("Album-Name", text: $name) }
                Section("Typ") {
                    Picker("Typ", selection: $type) {
                        Text("Normal").tag("manual")
                        Text("Smart").tag("smart")
                        Text("KI").tag("ai")
                    }.pickerStyle(.segmented)
                    switch type {
                    case "smart": Text("Füllt sich automatisch mit allen Fotos der gewählten Personen (kein Limit).")
                                    .font(.caption).foregroundStyle(.secondary)
                    case "ai":    Text("Gemini wählt passende Fotos zur Beschreibung aus.")
                                    .font(.caption).foregroundStyle(.secondary)
                    default:      Text("Fotos manuell hinzufügen.")
                                    .font(.caption).foregroundStyle(.secondary)
                    }
                }
                if type == "smart" {
                    Section("Personen") {
                        if selectedPeople.count > 1 {
                            Toggle("Müssen alle gemeinsam vorkommen", isOn: $requireAll)
                        }
                        ForEach(people.filter(isNamed)) { p in
                            Button {
                                if selectedPeople.contains(p.id) { selectedPeople.remove(p.id) }
                                else { selectedPeople.insert(p.id) }
                            } label: {
                                HStack {
                                    Avatar(url: api.url(p.avatar_url), initials: p.name.firstInitial, size: 32)
                                    Text(p.name).foregroundStyle(.primary)
                                    Spacer()
                                    if selectedPeople.contains(p.id) {
                                        Image(systemName: "checkmark.circle.fill").foregroundStyle(.indigo)
                                    }
                                }
                            }
                        }
                    }
                }
                if type == "ai" {
                    Section("Beschreibung") {
                        TextField("z. B. Sonnenuntergänge am Strand", text: $aiPrompt, axis: .vertical)
                            .lineLimit(2...5)
                    }
                }
                Section {
                    Button { Task { await save() } } label: {
                        HStack { if busy { ProgressView() }; Text("Speichern") }
                    }.disabled(!canSave)
                }
            }
            .navigationTitle("Album bearbeiten")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Abbrechen") { dismiss() } } }
            .onAppear { name = currentName; type = currentType }
            .task { if people.isEmpty { people = (try? await api.people()) ?? [] } }
        }
    }

    func save() async {
        busy = true; defer { busy = false }
        let n = name.trimmingCharacters(in: .whitespaces)
        var smart: [String: Any]? = nil
        var prompt: String? = nil
        switch type {
        case "smart":
            let c: [String: Any] = ["person_ids": Array(selectedPeople), "person_match": (selectedPeople.count > 1 && requireAll) ? "all" : "any"]
            smart = c
        case "ai":
            prompt = aiPrompt.trimmingCharacters(in: .whitespaces)
        default: break
        }
        try? await api.updateAlbum(album.id, name: n, type: type, smartCriteria: smart, aiPrompt: prompt)
        await onSaved(n, type)
        dismiss()
    }
}
