import SwiftUI

/// Home screen — greeting, library stats and horizontal strips (on-this-day,
/// person of the week, highlights, people, albums, recently added). Tapping a
/// photo opens the shared full-screen PhotoPager; tapping a person/album pushes
/// the existing detail screens. Backed by GET /api/v1/dashboard.
struct DashboardView: View {
    @EnvironmentObject var api: APIClient
    @State private var data: DashboardV1?
    @State private var loading = false
    @State private var error: String?
    @State private var selected: PhotoV1?
    @State private var userName = ""

    private var greeting: String {
        let h = Calendar.current.component(.hour, from: Date())
        let base: String
        switch h {
        case 5..<11:  base = "Guten Morgen"
        case 11..<17: base = "Hallo"
        case 17..<22: base = "Guten Abend"
        default:      base = "Gute Nacht"
        }
        return userName.isEmpty ? base : "\(base), \(userName)"
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                if let error { Text(error).foregroundStyle(.secondary).padding() }
                if let d = data {
                    VStack(alignment: .leading, spacing: 24) {
                        header
                        statTiles(d.stats)
                        ForEach(d.on_this_day) { day in
                            photoStrip(title: day.years_ago == 1 ? "Heute vor 1 Jahr"
                                                                  : "Heute vor \(day.years_ago) Jahren",
                                       items: day.items)
                        }
                        if let pow = d.person_of_week { personOfWeek(pow) }
                        photoStrip(title: "Highlights", items: d.highlights)
                        peopleStrip(d.featured_people)
                        albumsStrip(d.featured_albums)
                        photoStrip(title: "Zuletzt hinzugefügt", items: d.recent)
                    }
                    .padding(.vertical, 12)
                }
                if loading && data == nil { ProgressView().padding(.top, 80) }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Image("Logo").resizable().scaledToFit().frame(height: 26)
                }
            }
            .navigationDestination(for: PersonV1.self) { PersonDetailView(person: $0) }
            .navigationDestination(for: AlbumV1.self) { AlbumDetailView(album: $0) }
            .refreshable { await load() }
            .task { if data == nil { await load() } }
            .fullScreenCover(item: $selected) { p in
                PhotoPager(photos: pagerPool, start: p)
            }
        }
    }

    // All photos shown anywhere on the dashboard — so swiping in the pager has a
    // sensible pool to move through regardless of which strip was tapped.
    private var pagerPool: [PhotoV1] {
        guard let d = data else { return [] }
        var seen = Set<Int>(); var out: [PhotoV1] = []
        for p in d.on_this_day.flatMap({ $0.items }) + (d.person_of_week?.items ?? [])
                 + d.highlights + d.recent {
            if seen.insert(p.id).inserted { out.append(p) }
        }
        return out
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(greeting).font(.title2.bold())
            Text("Deine Erinnerungen auf einen Blick").font(.subheadline).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal)
    }

    @ViewBuilder private func statTiles(_ s: DashboardStats) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                statTile("Gesamt", s.total, "photo.on.rectangle.angled")
                statTile("Fotos", s.images, "photo")
                statTile("Videos", s.videos, "video.fill")
                statTile("Personen", s.with_faces, "person.2.fill")
                statTile("Beschrieben", s.described, "text.below.photo")
                statTile("Mit GPS", s.with_gps, "mappin.and.ellipse")
            }
            .padding(.horizontal)
        }
    }

    private func statTile(_ title: String, _ value: Int, _ icon: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: icon).font(.headline).foregroundStyle(.indigo)
            Text("\(value)").font(.title3.bold())
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .padding(12)
        .frame(width: 104, alignment: .leading)
        .background(.indigo.opacity(0.10), in: RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder private func photoStrip(title: String, items: [PhotoV1]) -> some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text(title).font(.headline).padding(.horizontal)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(items) { p in
                            stripTile(p)
                                .onTapGesture { selected = p }
                        }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }

    private func stripTile(_ p: PhotoV1) -> some View {
        Thumb(url: api.url("api/photos/\(p.id)/thumbnail?size=medium"))
            .frame(width: 130, height: 130)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(alignment: .bottomLeading) {
                if p.is_video {
                    Image(systemName: "play.fill").font(.caption2).foregroundStyle(.white)
                        .padding(5).shadow(radius: 2)
                }
            }
            .contentShape(Rectangle())
    }

    @ViewBuilder private func personOfWeek(_ pow: DashboardPersonOfWeek) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Person der Woche").font(.headline).padding(.horizontal)
            NavigationLink(value: PersonV1(id: pow.id, name: pow.name, face_count: pow.face_count,
                                           avatar_url: pow.avatar_url ?? "")) {
                HStack(spacing: 12) {
                    Avatar(url: pow.avatar_url.flatMap { api.url($0) },
                           initials: pow.name.firstInitial, size: 56)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(pow.name).font(.subheadline.weight(.semibold)).foregroundStyle(.primary)
                        Text("\(pow.face_count) Aufnahmen").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
                }
                .padding(.horizontal)
            }
            .buttonStyle(.plain)
            if !pow.items.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(pow.items) { p in
                            stripTile(p).onTapGesture { selected = p }
                        }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }

    @ViewBuilder private func peopleStrip(_ people: [DashboardPerson]) -> some View {
        if !people.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Personen").font(.headline).padding(.horizontal)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 14) {
                        ForEach(people) { person in
                            NavigationLink(value: PersonV1(id: person.id, name: person.name,
                                                           face_count: person.face_count,
                                                           avatar_url: person.avatar_url ?? "")) {
                                VStack(spacing: 6) {
                                    Avatar(url: person.avatar_url.flatMap { api.url($0) },
                                           initials: person.name.firstInitial, size: 64)
                                    Text(person.name).font(.caption).lineLimit(1)
                                        .frame(width: 72).foregroundStyle(.primary)
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }

    @ViewBuilder private func albumsStrip(_ albums: [DashboardAlbum]) -> some View {
        if !albums.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Alben").font(.headline).padding(.horizontal)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(albums) { a in
                            NavigationLink(value: AlbumV1(id: a.id, name: a.name, description: nil,
                                                          album_type: "manual",
                                                          photo_count: a.photo_count, cover_url: a.cover_url)) {
                                VStack(alignment: .leading, spacing: 6) {
                                    Thumb(url: a.cover_url.flatMap { api.url($0) })
                                        .frame(width: 150, height: 150)
                                        .background(Color.gray.opacity(0.15))
                                        .clipShape(RoundedRectangle(cornerRadius: 12))
                                    Text(a.name).font(.subheadline.weight(.medium)).lineLimit(1)
                                        .foregroundStyle(.primary)
                                    Text("\(a.photo_count) Fotos").font(.caption).foregroundStyle(.secondary)
                                }
                                .frame(width: 150)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                }
            }
        }
    }

    func load() async {
        loading = true; defer { loading = false }
        do { data = try await api.dashboard(); error = nil }
        catch { self.error = "Start-Seite konnte nicht geladen werden." }
        if userName.isEmpty {
            let n = await api.meName()
            if !n.isEmpty { userName = n.split(separator: " ").first.map(String.init) ?? n }
        }
    }
}
