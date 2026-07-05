import SwiftUI

struct PeopleView: View {
    let api: APIClient
    @State private var people: [PersonV1] = []
    @State private var isLoading = true
    @State private var selectedPerson: PersonV1? = nil

    private let columns = [GridItem(.adaptive(minimum: 240, maximum: 300), spacing: 32)]

    var body: some View {
        NavigationView {
            Group {
                if isLoading {
                    ProgressView("Lade Personen…")
                } else if people.isEmpty {
                    Label("Keine Personen erkannt", systemImage: "person.2")
                        .font(.title2).foregroundStyle(.secondary)
                } else {
                    ScrollView {
                        LazyVGrid(columns: columns, spacing: 32) {
                            ForEach(people) { person in
                                Button { selectedPerson = person } label: {
                                    PersonCard(person: person, api: api)
                                }
                                .buttonStyle(.card)
                            }
                        }
                        .padding(60)
                    }
                }
            }
            .navigationTitle("Personen")
        }
        .task {
            people = (try? await api.fetchPeople()) ?? []
            isLoading = false
        }
        .fullScreenCover(item: $selectedPerson) { person in
            NavigationView {
                GalleryView(api: api, personId: person.id, title: person.name)
                    .toolbar {
                        ToolbarItem(placement: .navigationBarLeading) {
                            Button("Schließen") { selectedPerson = nil }
                        }
                    }
            }
            .onExitCommand { selectedPerson = nil }
        }
    }
}

private struct PersonCard: View {
    let person: PersonV1
    let api: APIClient

    var body: some View {
        VStack(spacing: 12) {
            AuthAsyncImage(url: api.fixedURL(person.avatar_url), headers: api.authHeaders()) { img in
                img.resizable().aspectRatio(contentMode: .fill)
            } placeholder: {
                Circle().fill(Color.indigo.opacity(0.3))
                    .overlay(Image(systemName: "person.fill")
                        .font(.system(size: 40)).foregroundStyle(.white.opacity(0.5)))
            }
            .frame(width: 160, height: 160)
            .clipShape(Circle())

            Text(person.name)
                .font(.headline)
                .foregroundStyle(.white)
                .lineLimit(1)
            Text("\(person.photo_count) Fotos")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(24)
        .background(Color.white.opacity(0.06))
        .cornerRadius(20)
    }
}
