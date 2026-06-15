import SwiftUI

struct SettingsScreen: View {
    @EnvironmentObject var api: APIClient
    @State private var serverDraft = ""
    @State private var user = ""
    @State private var pass = ""
    @State private var loginError = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("http://host:8090", text: $serverDraft)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    Button("Speichern") { api.serverURL = serverDraft }
                }
                Section(api.loggedIn ? "Angemeldet" : "Anmelden") {
                    if api.loggedIn {
                        Button("Abmelden", role: .destructive) { Task { await api.logout() } }
                    } else {
                        TextField("E-Mail", text: $user).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.emailAddress)
                        SecureField("Passwort", text: $pass)
                        Button("Anmelden") {
                            Task { do { try await api.login(username: user, password: pass); pass = "" } catch { loginError = true } }
                        }
                    }
                    Text("Login ist nur nötig, wenn am Server „Login erzwingen" aktiv ist.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Section { Text("PhotoFlow iOS · v1.0") .font(.caption).foregroundStyle(.secondary) }
            }
            .navigationTitle("Einstellungen")
            .onAppear { serverDraft = api.serverURL }
            .alert("Anmeldung fehlgeschlagen", isPresented: $loginError) { Button("OK") {} }
        }
    }
}
