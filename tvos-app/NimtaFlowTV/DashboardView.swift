import SwiftUI

private struct DashResponse: Codable {
    struct Stats: Codable {
        let total: Int?
        let images: Int?
        let videos: Int?
        let with_faces: Int?
    }
    struct Memory: Codable {
        let years_ago: Int
        let date: String
        let items: [PhotoV1]
    }
    struct Person: Codable, Identifiable {
        let id: Int
        let name: String
        let photo_count: Int
        let avatar_url: String
        let items: [PhotoV1]?
    }
    struct Album: Codable, Identifiable {
        let id: Int
        let name: String
        let photo_count: Int
        let cover_url: String?
    }
    let stats: Stats?
    let on_this_day: [Memory]?
    let person_of_week: Person?
    let featured_albums: [Album]?
    let recent: [PhotoV1]?
}

struct DashboardView: View {
    let api: APIClient
    @State private var data: DashResponse? = nil
    @State private var selectedPhoto: PhotoV1? = nil

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 48) {
                    if let data {
                        if let stats = data.stats {
                            statsRow(stats)
                        }
                        if let recent = data.recent, !recent.isEmpty {
                            photoRow(title: "Zuletzt hinzugefügt", icon: "clock", photos: recent)
                        }
                        if let mem = data.on_this_day, !mem.isEmpty {
                            ForEach(mem, id: \.date) { m in
                                let title = m.years_ago == 1 ? "Vor 1 Jahr" : "Vor \(m.years_ago) Jahren"
                                photoRow(title: title, icon: "calendar", photos: m.items)
                            }
                        }
                    } else {
                        ProgressView("Lade…")
                            .frame(maxWidth: .infinity, minHeight: 400)
                    }
                }
                .padding(.horizontal, 60)
                .padding(.vertical, 48)
            }
            .navigationTitle("NimtaFlow")
        }
        .task { await load() }
        .fullScreenCover(item: $selectedPhoto) { photo in
            MediaPlayerView(photo: photo, api: api, onClose: { selectedPhoto = nil })
        }
    }

    @ViewBuilder
    private func statsRow(_ stats: DashResponse.Stats) -> some View {
        HStack(spacing: 24) {
            statCard(label: "Fotos & Videos", value: stats.total ?? 0, icon: "photo.stack", color: .indigo)
            statCard(label: "Fotos", value: stats.images ?? 0, icon: "photo", color: .blue)
            statCard(label: "Videos", value: stats.videos ?? 0, icon: "video", color: .purple)
            statCard(label: "Mit Gesichtern", value: stats.with_faces ?? 0, icon: "person.crop.square", color: .pink)
        }
    }

    @ViewBuilder
    private func statCard(label: String, value: Int, icon: String, color: Color) -> some View {
        VStack(spacing: 12) {
            Image(systemName: icon).font(.system(size: 32)).foregroundStyle(color)
            Text("\(value.formatted())").font(.title.bold()).foregroundStyle(.white)
            Text(label).font(.callout).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(24)
        .background(color.opacity(0.1))
        .cornerRadius(16)
    }

    @ViewBuilder
    private func photoRow(title: String, icon: String, photos: [PhotoV1]) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Label(title, systemImage: icon)
                .font(.title2.bold())
                .foregroundStyle(.white)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 20) {
                    ForEach(photos) { photo in
                        Button {
                            selectedPhoto = photo
                        } label: {
                            PhotoCard(photo: photo, api: api)
                        }
                        .buttonStyle(.card)
                    }
                }
                .padding(.horizontal, 4)
                .padding(.vertical, 8)
            }
        }
    }

    private func load() async {
        let req = api.buildRequest("api/v1/dashboard")
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let resp = try? JSONDecoder().decode(DashResponse.self, from: data)
        else { return }
        await MainActor.run { self.data = resp }
    }
}
