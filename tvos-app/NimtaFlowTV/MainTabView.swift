import SwiftUI

enum TVTab: String, CaseIterable {
    case home = "Zuhause"
    case gallery = "Galerie"
    case albums = "Alben"
    case people = "Personen"
    case slideshow = "Diashow"
    case settings = "Einstellungen"

    var icon: String {
        switch self {
        case .home: return "house"
        case .gallery: return "photo.on.rectangle"
        case .albums: return "rectangle.stack"
        case .people: return "person.2"
        case .slideshow: return "play.rectangle"
        case .settings: return "gearshape"
        }
    }
}

struct MainTabView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedTab: TVTab = .home

    var body: some View {
        TabView(selection: $selectedTab) {
            ForEach(TVTab.allCases, id: \.self) { tab in
                tabContent(tab)
                    .tabItem {
                        Label(tab.rawValue, systemImage: tab.icon)
                    }
                    .tag(tab)
            }
        }
    }

    @ViewBuilder
    private func tabContent(_ tab: TVTab) -> some View {
        switch tab {
        case .home:
            DashboardView(api: appState.api)
        case .gallery:
            GalleryView(api: appState.api)
        case .albums:
            AlbumsView(api: appState.api)
        case .people:
            PeopleView(api: appState.api)
        case .slideshow:
            SlideshowView(api: appState.api)
        case .settings:
            SettingsView(appState: appState)
        }
    }
}
