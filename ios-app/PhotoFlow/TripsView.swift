import SwiftUI

/// Auto-detected trips/events — cover, city, dates, count. Tapping opens the
/// event's photos (loaded by date range) in the shared full-screen pager.
struct TripsView: View {
    @EnvironmentObject var api: APIClient
    @State private var events: [TripEventV1] = []
    @State private var homeCity: String?
    @State private var tripsOnly = true
    @State private var loading = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                if let error { Text(error).foregroundStyle(.secondary).padding() }
                if let h = homeCity {
                    Text("Zuhause: \(h)").font(.footnote).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal).padding(.top, 4)
                }
                LazyVStack(spacing: 14) {
                    ForEach(events) { e in
                        NavigationLink(value: e) { TripCard(event: e) }.buttonStyle(.plain)
                    }
                }
                .padding(12)
                if loading { ProgressView().padding() }
                if !loading && events.isEmpty && error == nil {
                    ContentUnavailableView("Keine Reisen", systemImage: "airplane.departure",
                                           description: Text(tripsOnly ? "Schalte ‚Alle Events‘ ein, um auch Alltags-Cluster zu sehen." : "Noch keine Events erkannt."))
                        .padding(.top, 60)
                }
            }
            .navigationTitle("Reisen")
            .navigationDestination(for: TripEventV1.self) { TripDetailView(event: $0) }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Picker("", selection: $tripsOnly) {
                        Text("Reisen").tag(true); Text("Alle").tag(false)
                    }
                    .pickerStyle(.segmented).frame(width: 150)
                    .onChange(of: tripsOnly) { _, _ in Task { await load() } }
                }
            }
            .refreshable { await load() }
            .task { if events.isEmpty { await load() } }
        }
    }

    func load() async {
        loading = true; defer { loading = false }
        do {
            let r = try await api.trips(tripsOnly: tripsOnly)
            events = r.events; homeCity = r.home_city; error = nil
        } catch { self.error = "Reisen konnten nicht geladen werden." }
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
