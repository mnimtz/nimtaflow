import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        TabView {
            GalleryView(api: appState.api)
                .tabItem { Label("Galerie", systemImage: "photo.stack") }

            AlbumsView(api: appState.api)
                .tabItem { Label("Alben", systemImage: "rectangle.stack") }

            PeopleView(api: appState.api)
                .tabItem { Label("Personen", systemImage: "person.2") }

            SlideshowView(api: appState.api)
                .tabItem { Label("Diashow", systemImage: "play.rectangle.fill") }

            SettingsView()
                .tabItem { Label("Einstellungen", systemImage: "gear") }
        }
    }
}
