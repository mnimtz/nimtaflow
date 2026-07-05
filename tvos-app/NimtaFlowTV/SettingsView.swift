import SwiftUI

struct SettingsView: View {
    @ObservedObject var appState: AppState
    @State private var showLogoutConfirm = false
    @State private var versionInfo: String? = nil

    var body: some View {
        NavigationView {
            List {
                Section("Server") {
                    LabeledContent("URL", value: appState.api.serverURL)
                    if let ver = versionInfo {
                        LabeledContent("Version", value: ver)
                    }
                }

                Section("App") {
                    LabeledContent("App-Version", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "–")
                }

                Section {
                    Button(role: .destructive) {
                        showLogoutConfirm = true
                    } label: {
                        Label("Abmelden", systemImage: "rectangle.portrait.and.arrow.right")
                    }
                }
            }
            .navigationTitle("Einstellungen")
        }
        .task { await loadVersion() }
        .alert("Abmelden?", isPresented: $showLogoutConfirm) {
            Button("Abmelden", role: .destructive) { appState.logout() }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Du wirst vom Server abgemeldet.")
        }
    }

    private func loadVersion() async {
        let req = appState.api.buildRequest("api/version")
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let ver = json["version"] as? String
        else { return }
        versionInfo = ver
    }
}
