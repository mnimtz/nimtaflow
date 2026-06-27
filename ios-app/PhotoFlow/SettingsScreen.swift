import SwiftUI

struct SettingsScreen: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var store: Store
    @State private var serverDraft = ""
    @State private var user = ""
    @State private var pass = ""
    @State private var loginError = false
    @AppStorage("allow_self_signed") private var allowSelfSigned = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("https://login.nimtaflow.com", text: $serverDraft)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    Button("Speichern") { api.serverURL = serverDraft }
                    Toggle("Selbst-signierte Zertifikate akzeptieren", isOn: $allowSelfSigned)
                    Text("Nur nötig, wenn dein Server ein eigenes/selbst-signiertes SSL-Zertifikat nutzt. Bei Cloudflare/Let's Encrypt aus lassen.")
                        .font(.caption).foregroundStyle(.secondary)
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
                ProSection()
                if api.loggedIn && store.isPro { AutoUploadSection() }
                if api.loggedIn { RemindersSection() }
                CacheSection()
                if api.loggedIn { HighlightsMusicSection() }
                if api.loggedIn { HighlightsAISection() }
                Section {
                    let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
                    let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
                    Text("NimtaFlow · v\(v) (\(b))").font(.caption).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Einstellungen")
            .onAppear { serverDraft = api.serverURL }
            .alert("Anmeldung fehlgeschlagen", isPresented: $loginError) { Button("OK") {} }
        }
    }
}

/// NimtaFlow Pro: Status, Kauf, Wiederherstellen, Schlüssel einlösen.
private struct ProSection: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var api: APIClient
    @State private var code = ""
    @State private var redeeming = false
    @State private var redeemMsg: String?

    private var promoText: String {
        let f = DateFormatter(); f.dateFormat = "dd.MM.yyyy"
        return f.string(from: Store.promoEnd)
    }

    var body: some View {
        Section("NimtaFlow Pro") {
            if store.isPro {
                HStack {
                    Image(systemName: "crown.fill").foregroundStyle(.yellow)
                    if store.purchasedPro { Text("Pro aktiv — gekauft ✓") }
                    else if store.serverPro { Text("Pro aktiv — über deinen Server ✓") }
                    else { Text("Pro aktiv — Einführungsangebot bis \(promoText) 🎉") }
                }.font(.subheadline)
            }
            // Kauf bleibt erreichbar, solange nicht gekauft — auch während der Promo
            // (Apple-Reviewer kann den IAP testen; Unterstützer können früh kaufen).
            if !store.purchasedPro {
                Button {
                    Task { await store.purchase() }
                } label: {
                    HStack {
                        if store.purchasing { ProgressView().controlSize(.small) }
                        Text(store.isPro ? "NimtaFlow Pro unterstützen — \(store.priceText)" : "Pro freischalten — \(store.priceText)")
                    }
                }.disabled(store.purchasing || store.proProduct == nil)
                Button("Käufe wiederherstellen") { Task { await store.restore() } }
                    .font(.subheadline)
            }
            // Schlüssel einlösen (Server-Entitlement, z. B. für Familie)
            HStack {
                TextField("Schlüssel (NF-…)", text: $code)
                    .textInputAutocapitalization(.characters).autocorrectionDisabled()
                Button("Einlösen") {
                    Task {
                        redeeming = true; defer { redeeming = false }
                        do {
                            _ = try await api.action("api/auth/me/redeem", method: "POST", json: ["code": code])
                            await store.syncServer(api)
                            redeemMsg = store.serverPro ? "Schlüssel eingelöst — Pro aktiv ✓" : "Schlüssel nicht gültig."
                            code = ""
                        } catch { redeemMsg = "Schlüssel ungültig oder bereits benutzt." }
                    }
                }.disabled(redeeming || code.isEmpty)
            }
            if let m = redeemMsg { Text(m).font(.caption).foregroundStyle(.secondary) }
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
                .onChange(of: mgr.enabled) { _, on in
                    // Default OFF; when the user turns it ON for the first time, only
                    // upload photos from TODAY onward — never silently push the whole
                    // library's history. The user can move the date back deliberately.
                    if on && mgr.fromDateTS == 0 {
                        let today = Calendar.current.startOfDay(for: Date())
                        mgr.fromDate = today
                        fromDate = today
                    }
                    AutoUploadManager.scheduleBackground()
                }
            if mgr.enabled {
                DatePicker("Nur ab Datum", selection: $fromDate, displayedComponents: .date)
                    .onChange(of: fromDate) { _, d in mgr.fromDate = d }
                Text("Originale werden unverändert hochgeladen. Bereits hochgeladene werden übersprungen.")
                    .font(.caption).foregroundStyle(.secondary)

                // ── Bedingungen ───────────────────────────────────────────
                Toggle("Im Hintergrund (automatisch)", isOn: $mgr.background)
                    .onChange(of: mgr.background) { _, _ in AutoUploadManager.scheduleBackground() }
                Toggle("Nur über WLAN", isOn: $mgr.wifiOnly)
                    .onChange(of: mgr.wifiOnly) { _, _ in AutoUploadManager.scheduleBackground() }
                Toggle("Nur beim Laden", isOn: $mgr.requireCharging)
                    .onChange(of: mgr.requireCharging) { _, _ in AutoUploadManager.scheduleBackground() }
                Toggle("Bevorzugt nachts", isOn: $mgr.nightOnly)
                    .onChange(of: mgr.nightOnly) { _, _ in AutoUploadManager.scheduleBackground() }
                if mgr.nightOnly {
                    Stepper("Ab ca. \(mgr.nightHour) Uhr", value: $mgr.nightHour, in: 0...23)
                        .onChange(of: mgr.nightHour) { _, _ in AutoUploadManager.scheduleBackground() }
                }
                Text("Der Hintergrund-Upload läuft, wenn iOS es erlaubt — meist nachts beim Laden im WLAN. Den genauen Zeitpunkt bestimmt das System.")
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

/// Daily memories reminder (local notification).
private struct RemindersSection: View {
    @ObservedObject private var mgr = MemoryReminders.shared
    @State private var time = Date()

    var body: some View {
        Section("Erinnerungen") {
            Toggle("Tägliche Erinnerung", isOn: Binding(
                get: { mgr.enabled },
                set: { mgr.setEnabled($0) }))
            if mgr.enabled {
                DatePicker("Uhrzeit", selection: $time, displayedComponents: .hourAndMinute)
                    .onChange(of: time) { _, d in
                        let c = Calendar.current.dateComponents([.hour, .minute], from: d)
                        mgr.hour = c.hour ?? 10; mgr.minute = c.minute ?? 0
                        mgr.reschedule()
                    }
                Text("Eine tägliche Notiz erinnert dich an deine „Vor X Jahren\"-Erinnerungen.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .onAppear {
            time = Calendar.current.date(bySettingHour: mgr.hour, minute: mgr.minute, second: 0, of: Date()) ?? Date()
        }
    }
}

/// Local image cache: shows on-disk size and a "clear" button.
private struct CacheSection: View {
    @State private var sizeMB = imageCacheSizeMB()
    @State private var cleared = false
    var body: some View {
        Section("Speicher") {
            Button {
                clearImageCaches(); sizeMB = 0; cleared = true
            } label: {
                HStack {
                    Text("Bild-Cache leeren")
                    Spacer()
                    Text(cleared ? "geleert" : "\(sizeMB) MB").foregroundStyle(.secondary)
                }
            }
            Text("Lokal zwischengespeicherte Vorschau- und Großbilder. Werden bei Bedarf neu geladen.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .onAppear { sizeMB = imageCacheSizeMB(); cleared = false }
    }
}

/// Music + beat-sync for highlights — global default on/off, beat-sync, volume,
/// and the server-side music file path. Per-video override lives in the create flow.
private struct HighlightsMusicSection: View {
    @EnvironmentObject var api: APIClient
    @State private var enabled = true
    @State private var beatSync = true
    @State private var volume = "80"
    @State private var path = ""
    @State private var source = "file"      // file | library | generate
    @State private var model = "fal_open"   // local_fast | local_quality | remote | fal_open | fal_25
    @State private var budget = "50"
    @State private var falKey = ""
    @State private var prompt = ""
    @State private var tempo = ""
    @State private var energy = ""
    @State private var genre = ""
    @State private var libGen = false
    @State private var loaded = false
    @State private var saved = false

    var body: some View {
        Section("Musik & Beat-Sync (Highlights)") {
            Toggle("Musik unter Highlights", isOn: $enabled)
            if enabled {
                Toggle("Beat-Sync", isOn: $beatSync)
                HStack {
                    Text("Lautstärke (%)")
                    Spacer()
                    TextField("80", text: $volume).keyboardType(.numberPad)
                        .multilineTextAlignment(.trailing).frame(width: 60)
                }
                Picker("Musikquelle", selection: $source) {
                    Text("Eigene Datei").tag("file")
                    Text("CC0-Bibliothek").tag("library")
                    Text("KI erzeugen").tag("generate")
                }
                if source == "file" {
                    TextField("Musikdatei-Pfad (/cache/music/track.mp3)", text: $path)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                }
                if source == "generate" || source == "library" {
                    Picker("KI-Modell", selection: $model) {
                        Text("Lokal: Stable Audio (schnell)").tag("local_fast")
                        Text("Lokal: Stable Audio (Qualität)").tag("local_quality")
                        Text("Lokal auf M3 (Remote-Worker)").tag("remote")
                        Text("Cloud: fal Stable Audio").tag("fal_open")
                        Text("Cloud: fal Stable Audio 2.5").tag("fal_25")
                    }
                    if model.hasPrefix("fal") {
                        SecureField("fal API-Key (Musik) — leer = Video-Key", text: $falKey)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                    }
                }
                if source == "generate" {
                    TextField("Eigener Musik-Prompt (optional)", text: $prompt, axis: .vertical)
                        .lineLimit(1...3)
                    Picker("Tempo", selection: $tempo) {
                        Text("Automatisch").tag(""); Text("Langsam").tag("slow")
                        Text("Mittel").tag("medium"); Text("Schnell").tag("fast")
                    }
                    Picker("Energie", selection: $energy) {
                        Text("Automatisch").tag(""); Text("Ruhig").tag("calm")
                        Text("Ausgewogen").tag("balanced"); Text("Energiegeladen").tag("energetic")
                    }
                    TextField("Genre/Stil (z. B. Piano, Ambient)", text: $genre)
                        .textInputAutocapitalization(.never)
                    HStack {
                        Text("KI-Budget (Tracks/Monat)")
                        Spacer()
                        TextField("50", text: $budget).keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing).frame(width: 60)
                    }
                }
                if source == "library" {
                    Button(libGen ? "Erzeuge…" : "Bibliothek erzeugen") {
                        Task { libGen = true; defer { libGen = false }
                            try? await api.action("api/highlights/music-library/generate", method: "POST") }
                    }.disabled(libGen)
                }
            }
            Button(saved ? "✓ Gespeichert" : "Speichern") {
                Task {
                    let kv = ["highlights.music_enabled": enabled ? "true" : "false",
                              "highlights.beat_sync": beatSync ? "true" : "false",
                              "highlights.music_volume": volume,
                              "highlights.music_path": path,
                              "highlights.music_source": source,
                              "highlights.music_model": model,
                              "highlights.music_budget_month": budget,
                              "highlights.music_fal_key": falKey,
                              "highlights.music_prompt": prompt,
                              "highlights.music_tempo": tempo,
                              "highlights.music_energy": energy,
                              "highlights.music_genre": genre]
                    try? await api.saveSettings(kv)
                    saved = true
                    try? await Task.sleep(nanoseconds: 1_500_000_000); saved = false
                }
            }
            Text("Legt einen Soundtrack unter die Slideshow; Beat-Sync setzt die Übergänge auf den Takt. „KI erzeugen“ macht pro Video einen lizenzfreien Track (nur ein Stimmungs-Text geht in die Cloud, nie deine Fotos).")
                .font(.caption).foregroundStyle(.secondary)
        }
        .task {
            if loaded { return }; loaded = true
            if let s = try? await api.appSettings() {
                enabled = (s["highlights.music_enabled"] ?? "true") != "false"
                beatSync = (s["highlights.beat_sync"] ?? "true") != "false"
                volume = s["highlights.music_volume"] ?? "80"
                path = s["highlights.music_path"] ?? ""
                source = s["highlights.music_source"] ?? "file"
                model = s["highlights.music_model"] ?? "fal_open"
                budget = s["highlights.music_budget_month"] ?? "50"
                falKey = s["highlights.music_fal_key"] ?? ""
                prompt = s["highlights.music_prompt"] ?? ""
                tempo = s["highlights.music_tempo"] ?? ""
                energy = s["highlights.music_energy"] ?? ""
                genre = s["highlights.music_genre"] ?? ""
            }
        }
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
