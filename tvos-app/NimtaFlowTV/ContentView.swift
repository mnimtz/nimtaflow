import SwiftUI

struct ContentView: View {
    @EnvironmentObject var appState: AppState
    @State private var pendingServerURL: String = ""

    var body: some View {
        if appState.isLoggedIn {
            MainTabView()
                .environmentObject(appState)
        } else if !pendingServerURL.isEmpty {
            LoginView(serverURL: pendingServerURL, api: appState.api) { token in
                appState.login(serverURL: pendingServerURL, token: token)
            } onBack: {
                pendingServerURL = ""
            }
        } else {
            ServerSetupView { url in
                pendingServerURL = url
            }
        }
    }
}
