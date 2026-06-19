import SwiftUI

@main
struct PhotoFlowApp: App {
    @StateObject private var api = APIClient.shared
    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(api).preferredColorScheme(.dark)
        }
    }
}

struct RootView: View {
    @EnvironmentObject var api: APIClient
    var body: some View {
        if !api.loggedIn {
            LoginView()
        } else {
        TabView {
            GalleryView().tabItem { Label("Galerie", systemImage: "photo.on.rectangle.angled") }
            AlbumsView().tabItem { Label("Alben", systemImage: "rectangle.stack.fill") }
            SearchView().tabItem { Label("Suche", systemImage: "magnifyingglass") }
            ChatView().tabItem { Label("Chat", systemImage: "bubble.left.and.text.bubble.right.fill") }
            MoreView().tabItem { Label("Mehr", systemImage: "ellipsis.circle.fill") }
        }
        .tint(.indigo)
        }
    }
}

/// Overflow menu — keeps the tab bar to 5 items (mobile-first) while still
/// reaching Personen, Karte, Beziehungen and Einstellungen. Each opens as a
/// full-screen cover so the child's own NavigationStack/title bar is used
/// directly (no nested-stack double bars).
struct MoreView: View {
    private enum Dest: String, Identifiable {
        case people, trips, map, relationships, shares, settings
        var id: String { rawValue }
    }
    @State private var dest: Dest?

    var body: some View {
        NavigationStack {
            List {
                row("Personen", "person.2.fill", .people)
                row("Reisen", "airplane", .trips)
                row("Karte", "map.fill", .map)
                row("Beziehungen", "point.3.connected.trianglepath.dotted", .relationships)
                row("Geteilte Links", "link", .shares)
                row("Einstellungen", "gearshape.fill", .settings)
            }
            .navigationTitle("Mehr")
        }
        // Sheet with a drag handle to dismiss (swipe down) — no floating X that
        // would collide with each screen's own top-right toolbar buttons.
        .sheet(item: $dest) { d in
            Group {
                switch d {
                case .people: PeopleView()
                case .trips: TripsView()
                case .map: MapScreen()
                case .relationships: RelationshipsView()
                case .shares: SharesListView()
                case .settings: SettingsScreen()
                }
            }
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
    }

    @ViewBuilder private func row(_ title: String, _ icon: String, _ d: Dest) -> some View {
        Button { dest = d } label: {
            Label(title, systemImage: icon).foregroundStyle(.primary)
        }
    }
}
