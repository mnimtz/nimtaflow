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
            SearchView().tabItem { Label("Suche", systemImage: "magnifyingglass") }
            PeopleView().tabItem { Label("Personen", systemImage: "person.2.fill") }
            MapScreen().tabItem { Label("Karte", systemImage: "map.fill") }
            RelationshipsView().tabItem { Label("Beziehungen", systemImage: "point.3.connected.trianglepath.dotted") }
            SettingsScreen().tabItem { Label("Einstellungen", systemImage: "gearshape.fill") }
        }
        .tint(.indigo)
        }
    }
}
