import SwiftUI

/// Betriebs-/Leitstand-Status — Warteschlangen, Worker, Backlog, grobe Restzeit.
/// Nur für Administratoren (Endpoint /api/v1/ops ist admin-gated; die Menü-Zeile wird
/// zusätzlich über api.isAdmin ausgeblendet).
struct LeitstandView: View {
    @EnvironmentObject var api: APIClient
    @State private var ops: OpsStatus?
    @State private var loading = false
    @State private var err: String?

    var body: some View {
        NavigationStack {
            List {
                if let q = ops?.queues {
                    Section("Warteschlangen") {
                        row("CPU · Scans/Thumbnails", q.cpu)
                        row("GPU · KI/Gesichter", q.gpu)
                        row("Scan", q.scan)
                        row("Video · Transcode", q.video)
                    }
                }
                if let w = ops?.worker {
                    Section("Worker") {
                        let active = w.values.filter { $0 == "aktiv" }.count
                        HStack {
                            Image(systemName: active > 0 ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                                .foregroundStyle(active > 0 ? .green : .orange)
                            Text(active > 0 ? "\(active) aktiv" : "keine Antwort")
                        }
                    }
                }
                if let b = ops?.backlog {
                    Section("Backlog (offen, retryfähig)") {
                        row("Bilder ohne Beschreibung", b.bilder_ohne_beschreibung)
                        row("Videos ohne Beschreibung", b.videos_ohne_beschreibung)
                        row("Videos ohne Gesichts-Scan", b.videos_ohne_gesichtsscan)
                        row("Fehlerhafte Medien", b.fehlerhafte_medien)
                    }
                    let failedImg = b.bilder_beschreibung_fehlgeschlagen ?? 0
                    let failedVid = b.videos_beschreibung_fehlgeschlagen ?? 0
                    if failedImg + failedVid > 0 {
                        Section("Beschreibung fehlgeschlagen") {
                            row("Bilder", failedImg)
                            row("Videos", failedVid)
                            Button {
                                Task {
                                    _ = try? await api.resetAiErrors(kind: "all")
                                    await load()
                                }
                            } label: {
                                Label("Fehler zurücksetzen & neu versuchen", systemImage: "arrow.clockwise")
                            }
                        }
                    }
                }
                if let e = ops?.restzeit_schaetzung_minuten {
                    Section {
                        etaRow("GPU-Gesichter", e.gpu_gesichter)
                        etaRow("Bild-Beschreibungen", e.bild_beschreibungen)
                        etaRow("Video-Beschreibungen", e.video_beschreibungen)
                    } header: {
                        Text("Restzeit (grobe Schätzung)")
                    } footer: {
                        Text(ops?.hinweis_restzeit ?? "")
                    }
                }
                if let err { Text(err).foregroundStyle(.red) }
            }
            .navigationTitle("Leitstand")
            .toolbar { Button { Task { await load() } } label: { Image(systemName: "arrow.clockwise") } }
            .overlay { if loading && ops == nil { ProgressView() } }
            .task { await load() }
            .refreshable { await load() }
        }
    }

    @ViewBuilder private func row(_ title: String, _ v: Int?) -> some View {
        HStack {
            Text(title)
            Spacer()
            Text(v.map { String($0) } ?? "–").foregroundStyle(.secondary).monospacedDigit()
        }
    }

    @ViewBuilder private func etaRow(_ title: String, _ mins: Int?) -> some View {
        HStack { Text(title); Spacer(); Text(fmtMin(mins)).foregroundStyle(.secondary) }
    }

    private func fmtMin(_ m: Int?) -> String {
        guard let m, m > 0 else { return "–" }
        if m < 60 { return "\(m) Min" }
        let h = m / 60, r = m % 60
        return r > 0 ? "\(h) Std \(r) Min" : "\(h) Std"
    }

    private func load() async {
        loading = true; defer { loading = false }
        do { ops = try await api.opsStatus(); err = nil }
        catch { err = "Konnte Leitstand nicht laden (nur für Administratoren)." }
    }
}
