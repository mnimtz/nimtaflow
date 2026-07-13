import SwiftUI

/// v1.560: Neuer einheitlicher Leitstand — 6 Kacheln, identisch zu Web.
/// Datenquelle: GET /api/v1/leitstand — ein Endpoint, eine Wahrheit.
struct LeitstandView: View {
    @EnvironmentObject var api: APIClient
    @State private var data: LeitstandV2?
    @State private var loading = false
    @State private var err: String?
    @State private var refreshTask: Task<Void, Never>?
    @State private var actionMsg: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    if let e = err {
                        Text(e).font(.caption).foregroundStyle(.red).padding()
                    }
                    if let k = data?.kacheln {
                        descriptionsCard(k.descriptions)
                        videosCard(k.videos)
                        metadataCard(k.metadata)
                        peopleCard(k.people)
                        reingestCard(k.reingest)
                        if let s = k.special { specialCard(s) }
                        workersCard(workers: k.workers, queues: k.warteschlangen)
                    } else if loading {
                        ProgressView().padding()
                    } else {
                        Text("Keine Daten").foregroundStyle(.secondary).padding()
                    }
                }
                .padding(.horizontal)
                .padding(.vertical, 12)
            }
            .navigationTitle("Leitstand")
            .toolbar {
                if let ts = data?.updated_at {
                    ToolbarItem(placement: .topBarTrailing) {
                        Text("aktualisiert " + shortTime(ts))
                            .font(.caption2).foregroundStyle(.tertiary)
                    }
                }
            }
            .task { startAutoRefresh() }
            .onDisappear { refreshTask?.cancel() }
            .alert("Aktion", isPresented: Binding(
                get: { actionMsg != nil },
                set: { if !$0 { actionMsg = nil } })) {
                Button("OK") { actionMsg = nil }
            } message: {
                Text(actionMsg ?? "")
            }
        }
    }

    // MARK: - Auto-Refresh alle 3 s
    private func startAutoRefresh() {
        refreshTask?.cancel()
        refreshTask = Task {
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(nanoseconds: 3_000_000_000)
            }
        }
    }
    private func load() async {
        loading = true; defer { loading = false }
        do {
            data = try await api.leitstand()
            err = nil
        } catch {
            err = error.localizedDescription
        }
    }

    // MARK: - Kachel 1: Beschreibungen
    private func descriptionsCard(_ d: LeitstandV2.Descriptions) -> some View {
        card(title: d.title, systemImage: "text.document") {
            VStack(alignment: .leading, spacing: 12) {
                metricRow(label: "Freitext-Beschreibung", slice: d.text)
                metricRow(label: "Strukturiertes JSON (28 Felder)", slice: d.structured)
                if let r = d.structured.rate_pro_stunde, r > 0 {
                    Text("aktuell \(r.formatted()) Fotos/h neu strukturiert")
                        .font(.caption2).foregroundStyle(.secondary)
                        .monospacedDigit()
                }
                Text(d.detail)
                    .font(.caption2).foregroundStyle(.secondary)
                    .padding(.top, 4)
            }
        }
    }

    // MARK: - Kachel 2: Videos
    private func videosCard(_ v: LeitstandV2.Videos) -> some View {
        card(title: v.title, systemImage: "film") {
            VStack(alignment: .leading, spacing: 12) {
                metricRow(label: "1080p-Version bereit", slice: v.transcode)
                metricRow(label: "KI-Beschreibung", slice: v.beschreibung)
                if v.fehler > 0 {
                    HStack {
                        Text("\(v.fehler) Videos mit Fehler")
                            .font(.caption).foregroundStyle(.red)
                        Spacer()
                        Button("Cloud (Gemini) nachziehen") {
                            Task {
                                _ = try? await api.startVideoCloudFallback(limit: 500)
                                actionMsg = "Cloud-Fallback für bis zu 500 Videos gestartet."
                            }
                        }
                        .font(.caption).buttonStyle(.borderedProminent)
                    }
                }
            }
        }
    }

    // MARK: - Kachel 3: Metadaten
    private func metadataCard(_ m: LeitstandV2.Metadata) -> some View {
        card(title: m.title, systemImage: "doc.badge.arrow.up") {
            VStack(alignment: .leading, spacing: 12) {
                metricRow(label: "XMP-Sidecar geschrieben", slice: m.sidecar)
                Text(m.detail).font(.caption2).foregroundStyle(.secondary)
                if m.fehlend > 0 {
                    HStack {
                        Text("\(m.fehlend.formatted()) fehlen noch")
                            .font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button(m.action_label) {
                            Task {
                                _ = try? await api.startXmpBackfill(full: true)
                                actionMsg = "XMP-Backfill gestartet. Der Task läuft im Hintergrund; die Zahlen aktualisieren sich hier automatisch."
                            }
                        }
                        .font(.caption).buttonStyle(.borderedProminent)
                    }
                }
            }
        }
    }

    // MARK: - Kachel 4: Personen
    private func peopleCard(_ p: LeitstandV2.People) -> some View {
        card(title: p.title, systemImage: "person.2") {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                statTile("Benannte Personen", value: p.namen)
                statTile("Gesichter zugeordnet", value: p.faces_zugeordnet)
                statTile("Offene Gesichter", value: p.faces_offen,
                         tone: p.faces_offen > 1000 ? .warn : .ok)
                statTile("Vorschläge", value: p.faces_vorschlaege)
            }
        }
    }

    // MARK: - Kachel 5: Reingest
    private func reingestCard(_ r: LeitstandV2.Reingest) -> some View {
        card(title: r.title, systemImage: "arrow.triangle.2.circlepath") {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                statTile("In Bearbeitung", value: r.pending,
                         tone: r.pending > 0 ? .info : .ok)
                statTile("Gesamter Batch offen", value: r.in_batch)
                statTile("Letzte Stunde fertig", value: r.done_last_hour)
                if let e = r.eta_stunden {
                    statTileText("Restzeit (grob)", value: "\(Int(e)) h")
                } else {
                    statTileText("Restzeit (grob)", value: "—")
                }
            }
        }
    }

    // MARK: - Kachel 7: Spezial-Medien (v1.566)
    private func specialCard(_ s: LeitstandV2.Special) -> some View {
        card(title: s.title, systemImage: "globe") {
            VStack(alignment: .leading, spacing: 10) {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                    statTile("360°-Aufnahmen", value: s.erkannt_360, tone: .info)
                    statTile("Drohnen-Aufnahmen", value: s.erkannt_drone, tone: .info)
                    statTile("Noch zu prüfen", value: s.zu_pruefen,
                             tone: s.zu_pruefen > 100 ? .warn : .ok)
                    statTile("Little-Planet im Cache", value: s.little_planet_cached)
                }
                if s.zu_pruefen > 0 {
                    HStack {
                        Text("Erkennung läuft im Hintergrund.")
                            .font(.caption2).foregroundStyle(.secondary)
                        Spacer()
                        Button(s.action_label) {
                            Task {
                                _ = try? await api.startDetectSpecialMedia()
                                actionMsg = "Spezial-Medien-Erkennung neu gestartet."
                            }
                        }
                        .font(.caption).buttonStyle(.borderedProminent)
                    }
                }
            }
        }
    }

    // MARK: - Kachel 6: Worker
    private func workersCard(workers: [LeitstandV2.Worker], queues: [String: Int]) -> some View {
        card(title: "Worker-Fleet", systemImage: "cpu") {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(workers) { w in
                    HStack {
                        Circle()
                            .fill(workerColor(w.status))
                            .frame(width: 8, height: 8)
                        Text(w.name).font(.subheadline)
                        Spacer()
                        Text("\(w.rate_pro_stunde) /h")
                            .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                        Text("Ø \(Int(w.durchschnitt_sek))s")
                            .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                        Text(w.status == "offline" ? "offline" :
                                (w.letzte_arbeit_vor_sekunden.map { "\($0)s" } ?? "—"))
                            .font(.caption2).foregroundStyle(.tertiary).monospacedDigit()
                    }
                    .padding(8)
                    .background(Color.gray.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                }
                if workers.isEmpty {
                    Text("Keine Worker aktiv.").font(.caption).foregroundStyle(.secondary)
                }
                Divider().padding(.vertical, 4)
                HStack {
                    Text("Warteschlangen:").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Text(queuesShort(queues))
                        .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                }
            }
        }
    }

    // MARK: - Helfer
    @ViewBuilder
    private func card<Content: View>(title: String, systemImage: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: systemImage).foregroundStyle(.indigo)
                Text(title).font(.subheadline).bold()
            }
            content()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14))
    }

    private func metricRow(label: String, slice: LeitstandV2.Slice) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label).font(.caption).foregroundStyle(.secondary)
                Spacer()
                Text("\(slice.done.formatted()) / \(slice.total.formatted())")
                    .font(.caption2).foregroundStyle(.secondary).monospacedDigit()
            }
            HStack(spacing: 6) {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 4).fill(Color.gray.opacity(0.2)).frame(height: 6)
                        RoundedRectangle(cornerRadius: 4).fill(pctColor(slice.pct))
                            .frame(width: min(geo.size.width, geo.size.width * CGFloat(slice.pct / 100.0)), height: 6)
                    }
                }.frame(height: 6)
                Text("\(String(format: "%.1f", slice.pct))%")
                    .font(.caption2).foregroundStyle(.secondary).monospacedDigit()
                    .frame(width: 48, alignment: .trailing)
            }
        }
    }

    enum Tone { case ok, warn, info }
    private func statTile(_ label: String, value: Int, tone: Tone = .ok) -> some View {
        statTileText(label, value: value.formatted(), tone: tone)
    }
    private func statTileText(_ label: String, value: String, tone: Tone = .ok) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.title2.monospacedDigit()).bold()
                .foregroundStyle(toneColor(tone))
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func toneColor(_ t: Tone) -> Color {
        switch t { case .ok: return .primary; case .warn: return .orange; case .info: return .indigo }
    }
    private func pctColor(_ p: Double) -> Color {
        if p >= 95 { return .green }
        if p >= 60 { return .yellow }
        return .red
    }
    private func workerColor(_ s: String) -> Color {
        switch s { case "aktiv": return .green; case "idle": return .yellow; default: return .red }
    }
    private func queuesShort(_ q: [String: Int]) -> String {
        ["cpu", "gpu", "scan", "video"]
            .map { "\($0) \(q[$0] ?? 0)" }
            .joined(separator: " · ")
    }
    private func shortTime(_ iso: String) -> String {
        let df = ISO8601DateFormatter()
        guard let d = df.date(from: iso) else { return "—" }
        let out = DateFormatter(); out.dateFormat = "HH:mm:ss"
        return out.string(from: d)
    }
}
