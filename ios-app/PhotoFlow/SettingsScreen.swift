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
                    Text("Login ist nur nötig, wenn am Server ‚Login erzwingen‘ aktiv ist.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if api.loggedIn { AutoUploadSection() }
                if api.loggedIn { HighlightsAISection() }
                Section { Text("NimtaFlow iOS · v1.0") .font(.caption).foregroundStyle(.secondary) }
            }
            .navigationTitle("Einstellungen")
            .onAppear { serverDraft = api.serverURL }
            .alert("Anmeldung fehlgeschlagen", isPresented: $loginError) { Button("OK") {} }
        }
    }
}

/// Automatic camera-roll upload settings: on/off, a "from this date" lower bound,
/// plus a manual "upload now" trigger and live progress.
private struct AutoUploadSection: View {
    @EnvironmentObject var api: APIClient
    @ObservedObject private var mgr = AutoUploadManager.shared
    @State private var fromDate = Date()

    var body: some View {
        Section("Automatischer Upload") {
            Toggle("Automatisch hochladen", isOn: $mgr.enabled)
            if mgr.enabled {
                DatePicker("Nur ab Datum", selection: $fromDate, displayedComponents: .date)
                    .onChange(of: fromDate) { _, d in mgr.fromDate = d }
                Text("Es werden nur Aufnahmen ab diesem Datum automatisch hochgeladen. Bereits hochgeladene werden übersprungen.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Button {
                Task { await mgr.run(api: api) }
            } label: {
                HStack {
                    if mgr.running { ProgressView().controlSize(.small) }
                    Text(mgr.running ? "Lädt… \(mgr.done)/\(mgr.total)" : "Jetzt hochladen")
                }
            }
            .disabled(mgr.running || !api.loggedIn)
            if let r = mgr.lastResult {
                Text(r).font(.caption).foregroundStyle(.secondary)
            }
            Text("Uploads landen auf dem Server in deinem eigenen Upload-Ordner.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .onAppear { if mgr.fromDateTS > 0 { fromDate = mgr.fromDate } }
    }
}

/// KI-Video (Highlights) settings — enable + provider + key/budget, so the whole
/// "Foto animieren" feature is configurable from the phone, not only the web.
private struct HighlightsAISection: View {
    @EnvironmentObject var api: APIClient
    @State private var enabled = false
    @State private var provider = "fal"
    @State private var falKey = ""
    @State private var budget = "300"
    @State private var loaded = false
    @State private var saved = false

    var body: some View {
        Section("KI-Video (Highlights)") {
            Toggle("KI-Video aktivieren", isOn: $enabled)
            Picker("Anbieter", selection: $provider) {
                Text("fal.ai (günstig)").tag("fal")
                Text("Google Veo (Premium)").tag("veo")
                Text("Lokal auf M3").tag("local")
            }
            if provider == "fal" {
                SecureField("fal.ai API-Key", text: $falKey)
            }
            HStack {
                Text("Monatsbudget (Sek.)")
                Spacer()
                TextField("300", text: $budget).keyboardType(.numberPad)
                    .multilineTextAlignment(.trailing).frame(width: 80)
            }
            Button(saved ? "✓ Gespeichert" : "Speichern") {
                Task {
                    var kv = ["highlights.ai_enabled": enabled ? "true" : "false",
                              "highlights.ai_provider": provider,
                              "highlights.ai_budget_seconds_month": budget]
                    if provider == "fal", !falKey.isEmpty { kv["highlights.fal_api_key"] = falKey }
                    try? await api.saveSettings(kv)
                    saved = true
                    try? await Task.sleep(nanoseconds: 1_500_000_000); saved = false
                }
            }
            Text("Animiert Fotos zu Clips (✨ in der Foto-Ansicht). Kostenpflichtig je nach Anbieter; fal.ai bietet Gratis-Credits zum Testen.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .task {
            if loaded { return }
            loaded = true
            if let s = try? await api.appSettings() {
                enabled = (s["highlights.ai_enabled"] ?? "false") == "true"
                provider = s["highlights.ai_provider"] ?? "fal"
                budget = s["highlights.ai_budget_seconds_month"] ?? "300"
                // key intentionally not pre-filled (write-only via SecureField)
            }
        }
    }
}
