import SwiftUI

private enum TripFilter: String, CaseIterable {
    case all, auto, manual
    var label: String {
        switch self {
        case .all:    return "Alle"
        case .auto:   return "Automatisch"
        case .manual: return "Manuell"
        }
    }
}

/// Auto-detected trips/events — cover, city, dates, count. Tapping opens the
/// event’s photos (loaded by date range) in the shared full-screen pager.
struct TripsView: View {
    @EnvironmentObject var api: APIClient
    @AppStorage("trips_min_photos") private var minPhotos: Int = 8
    @AppStorage("trips_dismissed") private var dismissedRaw: String = ""
    @State private var events: [TripEventV1] = []
    @State private var storedTrips: [AlbumV1] = []
    @State private var homeCity: String?
    @State private var tripFilter: TripFilter = .all
    @State private var loading = false
    @State private var error: String?
    @State private var showSettings = false
    @State private var showWizard = false
    @State private var renaming: AlbumV1?
    @State private var renameText = ""

    private var dismissed: Set<String> {
        Set(dismissedRaw.split(separator: "\n").map(String.init))
    }
    private var visibleEvents: [TripEventV1] { events.filter { !dismissed.contains($0.id) } }

    func dismiss(_ e: TripEventV1) {
        var s = dismissed; s.insert(e.id); dismissedRaw = s.joined(separator: "\n")
    }
    func clearDismissed() { dismissedRaw = "" }

    // Gefilterte Listen je nach gewähltem Filter-Tab.
    private var shownManual: [AlbumV1] {
        tripFilter == .auto ? [] : storedTrips
    }
    private var shownAuto: [TripEventV1] {
        tripFilter == .manual ? [] : visibleEvents
    }
    private var isEmpty: Bool { shownManual.isEmpty && shownAuto.isEmpty }

    var body: some View {
        NavigationStack {
            ScrollView {
                if let error, isEmpty {
                    Text(error).foregroundStyle(.secondary).padding()
                }
                if let h = homeCity, tripFilter != .manual {
                    Text("Zuhause: \(h)").font(.footnote).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal).padding(.top, 4)
                }
                LazyVStack(spacing: 14) {
                    // Manuelle Reisen
                    ForEach(shownManual) { t in
                        NavigationLink(value: t) {
                            StoredTripCard(album: t, showBadge: tripFilter == .all)
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button { renameText = t.name; renaming = t } label: {
                                Label("Umbenennen", systemImage: "pencil")
                            }
                            Button(role: .destructive) {
                                Task { try? await api.deleteTrip(t.id); await load() }
                            } label: { Label("Reise löschen", systemImage: "trash") }
                        }
                    }
                    // Automatisch erkannte Reisen
                    ForEach(shownAuto) { e in
                        NavigationLink(value: e) {
                            TripCard(event: e, showBadge: tripFilter == .all)
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button(role: .destructive) { dismiss(e) } label: {
                                Label("Aus Liste entfernen", systemImage: "trash")
                            }
                        }
                    }
                }
                .padding(12)
                if loading { ProgressView().padding() }
                if !loading && isEmpty && error == nil {
                    ContentUnavailableView(
                        "Keine Reisen",
                        systemImage: "airplane.departure",
                        description: Text("Noch keine Reisen in dieser Kategorie. Lege über + eine an oder passe ‚min. Bilder’ in den Einstellungen an.")
                    ).padding(.top, 60)
                }
            }
            .navigationTitle("Reisen")
            .navigationDestination(for: TripEventV1.self) { TripDetailView(event: $0) }
            .navigationDestination(for: AlbumV1.self) { AlbumDetailView(album: $0) { Task { await load() } } }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showSettings = true } label: { Image(systemName: "slider.horizontal.3") }
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button { showWizard = true } label: { Image(systemName: "plus.circle.fill") }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Picker("", selection: $tripFilter) {
                        ForEach(TripFilter.allCases, id: \.self) { f in
                            Text(f.label).tag(f)
                        }
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 210)
                }
            }
            .sheet(isPresented: $showSettings) {
                TripsSettingsSheet(minPhotos: $minPhotos,
                                   dismissedCount: dismissed.count,
                                   onChange: { Task { await load() } },
                                   onRestore: clearDismissed)
                    .presentationDetents([.medium])
            }
            .sheet(isPresented: $showWizard) { NewTripWizard() }
            .alert("Reise umbenennen", isPresented: Binding(get: { renaming != nil },
                                                            set: { if !$0 { renaming = nil } })) {
                TextField("Name", text: $renameText)
                Button("Speichern") {
                    if let t = renaming {
                        let n = renameText.trimmingCharacters(in: .whitespaces)
                        if !n.isEmpty { Task { try? await api.renameAlbum(t.id, name: n); await load() } }
                    }
                    renaming = nil
                }
                Button("Abbrechen", role: .cancel) { renaming = nil }
            }
            .refreshable { await load() }
            .task { if events.isEmpty { await load() } }
        }
    }

    func load() async {
        loading = true; defer { loading = false }
        do {
            async let tripsResp = api.trips(tripsOnly: false, minPhotos: minPhotos)
            async let albumsResp = api.albums()
            let r = try await tripsResp
            events = r.events.filter { $0.is_trip }; homeCity = r.home_city; error = nil
            storedTrips = ((try? await albumsResp) ?? []).filter { $0.is_trip }
        } catch { self.error = "Reisen konnten nicht geladen werden." }
    }
}

/// Card for a stored trip-album (cover + name + photo count).
private struct StoredTripCard: View {
    @EnvironmentObject var api: APIClient
    let album: AlbumV1
    var showBadge: Bool = false

    var body: some View {
        Color.clear
            .aspectRatio(16.0/9.0, contentMode: .fit)
            .overlay {
                if let c = album.cover_url { Thumb(url: api.url(c)) }
                else { Color.gray.opacity(0.18) }
            }
            .overlay {
                LinearGradient(colors: [.clear, .black.opacity(0.65)], startPoint: .center, endPoint: .bottom)
            }
            .overlay(alignment: .bottomLeading) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Image(systemName: "airplane").font(.caption2)
                        Text(album.name).font(.headline)
                    }
                    Text("\(album.photo_count) Fotos").font(.caption)
                }
                .foregroundStyle(.white).padding(12)
            }
            .overlay(alignment: .topTrailing) {
                if showBadge {
                    Label("Manuell", systemImage: "pencil")
                        .font(.caption2).fontWeight(.medium)
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(.black.opacity(0.55), in: Capsule())
                        .foregroundStyle(.white)
                        .padding(10)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .contentShape(Rectangle())
    }
}

/// Reisen-Einstellungen: Mindestanzahl Fotos pro Event + ausgeblendete wiederherstellen.
private struct TripsSettingsSheet: View {
    @Binding var minPhotos: Int
    let dismissedCount: Int
    let onChange: () -> Void
    let onRestore: () -> Void
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Erkennung") {
                    Stepper(value: $minPhotos, in: 2...100) {
                        HStack { Text("min. Bilder pro Reise"); Spacer()
                            Text("\(minPhotos)").foregroundStyle(.secondary) }
                    }
                    .onChange(of: minPhotos) { _, _ in onChange() }
                    Text("Events mit weniger Fotos werden nicht als Reise angezeigt.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Section("Ausgeblendete Reisen") {
                    HStack { Text("Aus Liste entfernt"); Spacer()
                        Text("\(dismissedCount)").foregroundStyle(.secondary) }
                    Button("Alle wieder einblenden") { onRestore() }
                        .disabled(dismissedCount == 0)
                }
            }
            .navigationTitle("Reisen-Einstellungen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Fertig") { dismiss() } } }
        }
    }
}

private struct TripCard: View {
    @EnvironmentObject var api: APIClient
    let event: TripEventV1
    var showBadge: Bool = false

    var subtitle: String {
        let span = event.days > 1 ? "\(event.days) Tage" : "1 Tag"
        return "\(prettyDate(event.date_from)) · \(span) · \(event.count) Fotos"
    }

    var body: some View {
        Color.clear
            .aspectRatio(16.0/9.0, contentMode: .fit)
            .overlay {
                if let c = event.cover_url { Thumb(url: api.url(c)) }
                else { Color.gray.opacity(0.18) }
            }
            .overlay {
                LinearGradient(colors: [.clear, .black.opacity(0.65)], startPoint: .center, endPoint: .bottom)
            }
            .overlay(alignment: .bottomLeading) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        if event.is_trip { Image(systemName: "airplane").font(.caption2) }
                        Text(event.city ?? "Unbekannter Ort").font(.headline)
                    }
                    Text(subtitle).font(.caption)
                }
                .foregroundStyle(.white).padding(12)
            }
            .overlay(alignment: .topTrailing) {
                if showBadge {
                    Label("Automatisch", systemImage: "sparkles")
                        .font(.caption2).fontWeight(.medium)
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(Color.indigo.opacity(0.8), in: Capsule())
                        .foregroundStyle(.white)
                        .padding(10)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .contentShape(Rectangle())
    }
}

/// One trip's photos, loaded by its date range.
struct TripDetailView: View {
    @EnvironmentObject var api: APIClient
    let event: TripEventV1
    @State private var photos: [PhotoV1] = []
    @State private var cursor: Int? = nil
    @State private var hasMore = true
    @State private var loading = false
    @State private var selected: PhotoV1?
    @State private var showShare = false
    @State private var showRoute = false
    @AppStorage("trips_dismissed") private var dismissedRaw: String = ""
    @Environment(\.dismiss) private var dismiss

    let cols = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    private var routePhotos: [PhotoV1] {
        photos.filter { $0.latitude != nil && $0.longitude != nil }
            .sorted { ($0.taken_at ?? "") < ($1.taken_at ?? "") }
    }

    private func removeFromList() {
        var s = Set(dismissedRaw.split(separator: "\n").map(String.init))
        s.insert(event.id); dismissedRaw = s.joined(separator: "\n")
        dismiss()
    }

    var body: some View {
        PhotoGridView(photos: photos, onReachEnd: { Task { await load() } })
        .navigationTitle(event.city ?? "Reise")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    if routePhotos.count > 1 {
                        Button { showRoute = true } label: { Label("Route abspielen", systemImage: "play.circle") }
                    }
                    Button { showShare = true } label: { Label("Teilen", systemImage: "square.and.arrow.up") }
                    Button(role: .destructive) { removeFromList() } label: {
                        Label("Aus Liste entfernen", systemImage: "trash")
                    }
                } label: { Image(systemName: "ellipsis.circle") }
            }
        }
        .safeAreaInset(edge: .top) {
            Text("\(event.count) Fotos · \(prettyDate(event.date_from))")
                .font(.caption).foregroundStyle(.secondary).padding(.vertical, 4)
        }
        .task { if photos.isEmpty { await load() } }
        .sheet(isPresented: $showShare) {
            ShareSheetView(target: .trip(from: event.date_from, to: event.date_to,
                                         title: event.city ?? "Reise")).presentationDetents([.medium])
        }
        .sheet(isPresented: $showRoute) {
            RoutePlayerView(photos: routePhotos)
        }
    }

    func load() async {
        guard hasMore, !loading else { return }
        loading = true; defer { loading = false }
        do {
            let page = try await api.photosByDate(from: event.date_from, to: event.date_to, cursor: cursor)
            photos += page.items; cursor = page.next_cursor; hasMore = page.has_more
        } catch { hasMore = false }
    }
}

func prettyDate(_ iso: String) -> String {
    let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
    guard let d = f.date(from: iso) else { return iso }
    let o = DateFormatter(); o.locale = Locale(identifier: "de_DE"); o.dateFormat = "d. MMM yyyy"
    return o.string(from: d)
}

/// "Neue Reise" — describe a trip, Gemini plans the itinerary (waypoints), then
/// create an album that auto-fills with the photos in that date range.
struct NewTripWizard: View {
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss

    @State private var desc = ""
    @State private var tripType = "Pauschalurlaub"
    @State private var useDates = false
    @State private var from = Date()
    @State private var to = Date()
    @State private var phase = 0          // 0 = form, 1 = preview

    private let tripTypes = ["Pauschalurlaub", "Kreuzfahrt", "Flugreise", "Roadtrip",
                             "Rundreise", "Dienstreise", "Städtereise"]
    @State private var busy = false
    @State private var plan: TripPlan?
    @State private var error: String?
    @State private var createdName: String?
    @State private var createdAlbumId: Int?

    private var iso: DateFormatter { let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; return f }

    var body: some View {
        NavigationStack {
            Form {
                if let createdName {
                    Section { Label("Reise „\(createdName)“ erstellt — sie erscheint unter Alben.",
                                    systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                    if let aid = createdAlbumId {
                        Section {
                            Button(role: .destructive) {
                                Task {
                                    busy = true; defer { busy = false }
                                    try? await api.deleteTrip(aid)
                                    dismiss()
                                }
                            } label: {
                                HStack { if busy { ProgressView() }
                                    Text("Reise wieder löschen") }
                            }.disabled(busy)
                        }
                    }
                } else if phase == 0 {
                    Section("Reise beschreiben") {
                        TextField("z. B. Kreuzfahrt Norwegen, Juli 2023", text: $desc, axis: .vertical).lineLimit(2...4)
                        Picker("Art der Reise", selection: $tripType) {
                            ForEach(tripTypes, id: \.self) { Text($0).tag($0) }
                        }
                        Toggle("Zeitraum angeben", isOn: $useDates)
                        if useDates {
                            DatePicker("Von", selection: $from, displayedComponents: .date)
                            DatePicker("Bis", selection: $to, displayedComponents: .date)
                        }
                    }
                    if let error { Section { Text(error).foregroundStyle(.red).font(.footnote) } }
                    Section {
                        Button { Task { await planIt() } } label: {
                            HStack { if busy { ProgressView() }; Text("Mit Gemini planen") }
                        }.disabled(busy || desc.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                } else if let p = plan {
                    Section(p.name) {
                        if let s = p.summary, !s.isEmpty { Text(s).font(.callout) }
                    }
                    Section("Stationen (\(p.waypoints.count))") {
                        ForEach(Array(p.waypoints.enumerated()), id: \.offset) { _, w in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(w.place).font(.subheadline.weight(.medium))
                                if let n = w.note, !n.isEmpty { Text(n).font(.caption).foregroundStyle(.secondary) }
                            }
                        }
                    }
                    if let error { Section { Text(error).foregroundStyle(.red).font(.footnote) } }
                    Section {
                        Button { Task { await createIt() } } label: {
                            HStack { if busy { ProgressView() }; Text("Reise-Album erstellen") }
                        }.disabled(busy)
                        Button("Zurück") { phase = 0 }
                    }
                }
            }
            .navigationTitle("Neue Reise")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Schließen") { dismiss() } } }
        }
    }

    func planIt() async {
        busy = true; defer { busy = false }; error = nil
        do {
            plan = try await api.planTrip(description: desc,
                dateFrom: useDates ? iso.string(from: from) : nil,
                dateTo: useDates ? iso.string(from: to) : nil,
                tripType: tripType)
            phase = 1
        } catch {
            if let e = error as? APIClient.APIError {
                switch e {
                case .status(let c): self.error = "Server-Fehler \(c) bei der Planung."
                case .decode: self.error = "Antwort von Gemini nicht lesbar — bitte nochmal versuchen."
                case .badURL: self.error = "Server-Adresse ungültig."
                }
            } else {
                self.error = "Planung fehlgeschlagen: \((error as NSError).localizedDescription)"
            }
        }
    }

    func createIt() async {
        guard let p = plan else { return }
        busy = true; defer { busy = false }; error = nil
        do {
            let r = try await api.createTrip(p)
            createdName = r.name; createdAlbumId = r.album_id
        }
        catch { self.error = "Album konnte nicht erstellt werden." }
    }
}
