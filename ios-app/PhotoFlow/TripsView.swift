import SwiftUI

/// Auto-detected trips/events — cover, city, dates, count. Tapping opens the
/// event's photos (loaded by date range) in the shared full-screen pager.
struct TripsView: View {
    @EnvironmentObject var api: APIClient
    @AppStorage("trips_min_photos") private var minPhotos: Int = 8
    @AppStorage("trips_dismissed") private var dismissedRaw: String = ""
    @State private var events: [TripEventV1] = []
    @State private var homeCity: String?
    @State private var tripsOnly = true
    @State private var loading = false
    @State private var error: String?
    @State private var showSettings = false

    private var dismissed: Set<String> {
        Set(dismissedRaw.split(separator: "\n").map(String.init))
    }
    private var visibleEvents: [TripEventV1] { events.filter { !dismissed.contains($0.id) } }

    func dismiss(_ e: TripEventV1) {
        var s = dismissed; s.insert(e.id); dismissedRaw = s.joined(separator: "\n")
    }
    func clearDismissed() { dismissedRaw = "" }

    var body: some View {
        NavigationStack {
            ScrollView {
                if let error { Text(error).foregroundStyle(.secondary).padding() }
                if let h = homeCity {
                    Text("Zuhause: \(h)").font(.footnote).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal).padding(.top, 4)
                }
                LazyVStack(spacing: 14) {
                    ForEach(visibleEvents) { e in
                        NavigationLink(value: e) { TripCard(event: e) }
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
                if !loading && visibleEvents.isEmpty && error == nil {
                    ContentUnavailableView("Keine Reisen", systemImage: "airplane.departure",
                                           description: Text(tripsOnly ? "Schalte ‚Alle‘ ein oder senke ‚min. Bilder‘ in den Einstellungen." : "Noch keine Events erkannt."))
                        .padding(.top, 60)
                }
            }
            .navigationTitle("Reisen")
            .navigationDestination(for: TripEventV1.self) { TripDetailView(event: $0) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showSettings = true } label: { Image(systemName: "slider.horizontal.3") }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Picker("", selection: $tripsOnly) {
                        Text("Reisen").tag(true); Text("Alle").tag(false)
                    }
                    .pickerStyle(.segmented).frame(width: 150)
                    .onChange(of: tripsOnly) { _, _ in Task { await load() } }
                }
            }
            .sheet(isPresented: $showSettings) {
                TripsSettingsSheet(minPhotos: $minPhotos,
                                   dismissedCount: dismissed.count,
                                   onChange: { Task { await load() } },
                                   onRestore: clearDismissed)
                    .presentationDetents([.medium])
            }
            .refreshable { await load() }
            .task { if events.isEmpty { await load() } }
        }
    }

    func load() async {
        loading = true; defer { loading = false }
        do {
            let r = try await api.trips(tripsOnly: tripsOnly, minPhotos: minPhotos)
            events = r.events; homeCity = r.home_city; error = nil
        } catch { self.error = "Reisen konnten nicht geladen werden." }
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

    var subtitle: String {
        let span = event.days > 1 ? "\(event.days) Tage" : "1 Tag"
        return "\(prettyDate(event.date_from)) · \(span) · \(event.count) Fotos"
    }

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            if let c = event.cover_url {
                Thumb(url: api.url(c)).aspectRatio(16.0/9.0, contentMode: .fill)
            } else {
                Color.gray.opacity(0.18).aspectRatio(16.0/9.0, contentMode: .fill)
            }
            LinearGradient(colors: [.clear, .black.opacity(0.65)], startPoint: .center, endPoint: .bottom)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    if event.is_trip { Image(systemName: "airplane").font(.caption2) }
                    Text(event.city ?? "Unbekannter Ort").font(.headline)
                }
                Text(subtitle).font(.caption)
            }
            .foregroundStyle(.white).padding(12)
        }
        .frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 16))
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

    let cols = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: cols, spacing: 2) {
                ForEach(photos) { p in
                    Thumb(url: api.url(p.thumb_medium_url))
                        .aspectRatio(1, contentMode: .fill).frame(minHeight: 110)
                        .overlay(alignment: .bottomLeading) {
                            if p.is_video { Image(systemName: "play.fill").font(.caption2).foregroundStyle(.white).padding(4).shadow(radius: 2) }
                        }
                        .contentShape(Rectangle())
                        .onTapGesture { selected = p }
                        .onAppear { if p.id == photos.last?.id { Task { await load() } } }
                }
            }
            .padding(2)
            if loading { ProgressView().padding() }
        }
        .navigationTitle(event.city ?? "Reise")
        .navigationBarTitleDisplayMode(.inline)
        .task { if photos.isEmpty { await load() } }
        .fullScreenCover(item: $selected) { p in PhotoPager(photos: photos, start: p) }
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
