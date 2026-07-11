import SwiftUI

/// Betriebs-/Leitstand-Status — Warteschlangen, Worker, Backlog, grobe Restzeit.
/// Nur für Administratoren (Endpoint /api/v1/ops ist admin-gated; die Menü-Zeile wird
/// zusätzlich über api.isAdmin ausgeblendet).
struct LeitstandView: View {
    @EnvironmentObject var api: APIClient
    @State private var ops: OpsStatus?
    @State private var workers: OpsWorkers?
    @State private var loading = false
    @State private var err: String?
    @State private var refreshTask: Task<Void, Never>?

    var body: some View {
        NavigationStack {
            List {
                if let w = workers {
                    Section("Worker-Fortschritt") {
                        progressRow(lane: w.embed, iconName: "brain.head.profile")
                        progressRow(lane: w.xmp, iconName: "doc.badge.arrow.up")
                        if let vt = w.video_transcode {
                            progressRow(lane: vt, iconName: "film.stack")
                            HStack(spacing: 12) {
                                Text("720p neu: \(vt.done_720 ?? vt.done)").font(.caption).monospacedDigit()
                                Text("· 1080p neu: \(vt.done_1080 ?? 0)").font(.caption).foregroundStyle(.secondary).monospacedDigit()
                                if let leg = vt.legacy_only, leg > 0 {
                                    Text("· \(leg) alt (ruckelt)").font(.caption).foregroundStyle(.orange).monospacedDigit()
                                }
                            }
                            if (vt.legacy_only ?? 0) > 0 {
                                Button {
                                    Task {
                                        _ = try? await api.startVideoRequeueHdr(limit: 500)
                                        await load()
                                    }
                                } label: {
                                    Label("500 alte HDR-Videos neu transcodieren", systemImage: "arrow.clockwise.circle")
                                }
                            }
                        }
                        if let run = w.xmp.active_run, run.finished != true, let t = run.total, let d = run.done, t > 0 {
                            HStack {
                                Text("Aktueller XMP-Run").font(.caption).foregroundStyle(.secondary)
                                Spacer()
                                Text("\(d)/\(t) · \(run.failed ?? 0) Fehler")
                                    .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                            }
                        }
                        Button {
                            Task { _ = try? await api.startXmpBackfill(full: true); await load() }
                        } label: {
                            Label("XMP-Backfill jetzt starten (voll)", systemImage: "play.circle")
                        }
                    }
                }
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
                            if failedVid > 0 {
                                Button {
                                    Task {
                                        _ = try? await api.startVideoCloudFallback(limit: 200)
                                        await load()
                                    }
                                } label: {
                                    Label("Videos via Gemini nachziehen (Cloud)", systemImage: "cloud.and.arrow.up")
                                }
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
            .task {
                await load()
                // Auto-Refresh alle 10s solange der Screen offen ist — dann sieht
                // man den Progress live ohne manuell zu ziehen.
                refreshTask?.cancel()
                refreshTask = Task {
                    while !Task.isCancelled {
                        try? await Task.sleep(nanoseconds: 10_000_000_000)
                        if !Task.isCancelled { await load() }
                    }
                }
            }
            .onDisappear { refreshTask?.cancel(); refreshTask = nil }
            .refreshable { await load() }
        }
    }

    @ViewBuilder private func progressRow(lane: OpsWorkers.Lane, iconName: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: iconName).foregroundStyle(.indigo)
                Text(lane.label).font(.subheadline)
                Spacer()
                if let alive = lane.workers_alive, alive > 0 {
                    Image(systemName: "circle.fill").foregroundStyle(.green).font(.caption2)
                    Text("\(alive)").font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }
            }
            ProgressView(value: max(0, min(1, lane.percent / 100.0)))
            HStack {
                Text("\(lane.done) / \(lane.total)").font(.caption).monospacedDigit()
                Spacer()
                Text(String(format: "%.1f %%", min(100.0, max(0.0, lane.percent))))
                    .font(.caption).foregroundStyle(.secondary).monospacedDigit()
            }
        }.padding(.vertical, 2)
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
        do {
            async let a = api.opsStatus()
            async let b = api.opsWorkers()
            let (o, w) = try await (a, b)
            ops = o; workers = w; err = nil
        } catch {
            err = "Konnte Leitstand nicht laden (nur für Administratoren)."
        }
    }
}
