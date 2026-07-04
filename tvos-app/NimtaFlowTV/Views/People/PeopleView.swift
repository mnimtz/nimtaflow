import SwiftUI

struct PeopleView: View {
    let api: APIClient
    @State private var persons: [PersonV1] = []
    @State private var isLoading = true

    private let columns = [GridItem(.adaptive(minimum: 200), spacing: 32)]

    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    VStack(spacing: 16) { ProgressView(); Text("Lade Personen…").foregroundStyle(.secondary) }
                } else if persons.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "person.2").font(.system(size: 60)).foregroundStyle(.secondary)
                        Text("Keine Personen mit Fotos").foregroundStyle(.secondary)
                    }
                } else {
                    ScrollView {
                        LazyVGrid(columns: columns, spacing: 32) {
                            ForEach(persons) { person in
                                NavigationLink(destination: PersonDetailView(person: person, api: api)) {
                                    PersonCard(person: person, api: api)
                                }
                                .buttonStyle(.card)
                            }
                        }
                        .focusSection()
                        .padding(60)
                    }
                }
            }
            .navigationTitle("Personen")
        }
        .task {
            if let fetched = try? await api.fetchPeople() {
                persons = fetched
                isLoading = false
            }
        }
    }
}

struct PersonCard: View {
    let person: PersonV1
    let api: APIClient

    var body: some View {
        VStack(spacing: 12) {
            AuthAsyncImage(url: api.fixedURL(person.avatar_url), headers: api.authHeaders()) { img in
                img.resizable().aspectRatio(contentMode: .fill)
            } placeholder: {
                Circle().fill(Color.secondary.opacity(0.3))
                    .overlay(Image(systemName: "person.fill").font(.largeTitle).foregroundStyle(.secondary))
            }
            .frame(width: 160, height: 160)
            .clipShape(Circle())

            VStack(spacing: 4) {
                Text(person.name).font(.headline).lineLimit(1)
                Text("\(person.photo_count) Fotos").font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .frame(width: 200)
    }
}

struct PersonDetailView: View {
    let person: PersonV1
    let api: APIClient

    @State private var photos: [PhotoV1] = []
    @State private var isLoading = true
    @State private var hasMore = true
    @State private var nextCursor: Int? = nil

    private let columns = [GridItem(.adaptive(minimum: 280), spacing: 20)]

    var body: some View {
        Group {
            if isLoading && photos.isEmpty {
                VStack(spacing: 16) { ProgressView(); Text("Lade Fotos…").foregroundStyle(.secondary) }
            } else {
                ScrollView {
                    LazyVGrid(columns: columns, spacing: 20) {
                        ForEach(photos) { photo in
                            NavigationLink(destination: MediaPlayerView(photo: photo, photos: photos, api: api)) {
                                PhotoCard(photo: photo, api: api)
                            }
                            .buttonStyle(.card)
                        }
                    }
                    .focusSection()
                    .padding(60)

                    if hasMore {
                        Button("Mehr laden") { Task { await load() } }
                            .buttonStyle(.bordered).padding(20)
                    }
                }
            }
        }
        .navigationTitle(person.name)
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        if let page = try? await api.fetchPersonPhotos(personId: person.id, cursor: nextCursor) {
            photos += page.items
            nextCursor = page.next_cursor
            hasMore = page.has_more
        }
        isLoading = false
    }
}
