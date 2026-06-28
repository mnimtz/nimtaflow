import SwiftUI

@main
struct PhotoFlowApp: App {
    @StateObject private var api = APIClient.shared
    @StateObject private var store = Store()
    @Environment(\.scenePhase) private var scenePhase

    init() {
        // Must register the background-upload handler before launch finishes.
        AutoUploadManager.registerBackgroundTask()
    }

    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(api).environmentObject(store).preferredColorScheme(.dark)
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active:
                Task { await AutoUploadManager.shared.runIfEnabled(api: api) }
                MemoryReminders.shared.sync()
            case .background:
                // Queue an opportunistic background upload (iOS picks the moment —
                // typically at night while charging on Wi-Fi).
                AutoUploadManager.scheduleBackground()
            default: break
            }
        }
    }
}

struct RootView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var store: Store
    var body: some View {
        if !api.loggedIn {
            LoginView()
        } else {
        TabView {
            DashboardView().tabItem { Label("Start", systemImage: "house.fill") }
            GalleryView().tabItem { Label("Galerie", systemImage: "photo.on.rectangle.angled") }
            AlbumsView().tabItem { Label("Alben", systemImage: "rectangle.stack.fill") }
            ProGate(feature: "KI-Chat") { ChatView() }
                .tabItem { Label("Chat", systemImage: "bubble.left.and.text.bubble.right.fill") }
            MoreView().tabItem { Label("Mehr", systemImage: "ellipsis.circle.fill") }
        }
        .tint(.indigo)
        .task { await store.syncServer(api) }
        }
    }
}

/// Overflow menu — keeps the tab bar to 5 items (mobile-first) while still
/// reaching Personen, Karte, Beziehungen and Einstellungen. Each opens as a
/// full-screen cover so the child's own NavigationStack/title bar is used
/// directly (no nested-stack double bars).
struct MoreView: View {
    private enum Dest: String, Identifiable {
        case search, library, people, pets, memories, highlights, trips, map, relationships, shares, settings
        var id: String { rawValue }
    }
    @State private var dest: Dest?

    var body: some View {
        NavigationStack {
            List {
                row("Suche", "magnifyingglass", .search)
                row("Bibliothek", "chart.bar.fill", .library)
                row("Personen", "person.2.fill", .people)
                row("Haustiere", "pawprint.fill", .pets)
                row("Erinnerungen", "sparkles", .memories)
                row("Highlights", "sparkles.tv", .highlights)
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
                case .search: ProGate(feature: "Intelligente Suche") { SearchView() }
                case .library: LibraryStatsView()
                case .people: PeopleView()
                case .pets: PetsView()
                case .memories: MemoriesView()
                case .highlights: ProGate(feature: "Highlights") { HighlightsView() }
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
