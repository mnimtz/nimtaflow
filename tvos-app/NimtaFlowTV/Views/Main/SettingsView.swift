import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @State private var showLogoutConfirm = false

    var body: some View {
        NavigationStack {
            List {
                Section("Server") {
                    LabeledContent("Adresse", value: appState.api.serverURL)
                }

                Section {
                    Button("Abmelden", role: .destructive) {
                        showLogoutConfirm = true
                    }
                }
            }
            .navigationTitle("Einstellungen")
        }
        .confirmationDialog("Abmelden?", isPresented: $showLogoutConfirm) {
            Button("Abmelden", role: .destructive) { appState.logout() }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Du wirst vom Server abgemeldet und musst dich erneut anmelden.")
        }
    }
}
