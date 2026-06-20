import SwiftUI

/// "Bibliothek" — the at-a-glance totals: how many images vs videos the scan
/// found, how much is still processing, AI/faces coverage, and the date span.
struct LibraryStatsView: View {
    @EnvironmentObject var api: APIClient
    @State private var s: LibraryStats?
    @State private var scan: ScanProgress?
    @State private var loading = false
    @State private var loadError: String?

    private let cols = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        NavigationStack {
            ScrollView {
                if loading && s == nil { ProgressView().padding(.top, 60) }
                if let loadError, s == nil {
                    ContentUnavailableView {
                        Label("Statistik konnte nicht geladen werden", systemImage: "exclamationmark.triangle")
                    } description: { Text(loadError) } actions: {
                        Button("Erneut versuchen") { Task { await load() } }
                    }.padding(.top, 60)
                }
                if let s {
                    VStack(spacing: 16) {
                        // Live scan banner — addresses "no total shown during the scan".
                        if let scan, scan.running, scan.total > 0 {
                            let pct = Int(Double(scan.scanned) / Double(scan.total) * 100)
                            VStack(spacing: 6) {
                                HStack {
                                    Image(systemName: "magnifyingglass.circle.fill").foregroundStyle(.blue)
                                    Text("Scan läuft").font(.subheadline.bold())
                                    Spacer()
                                    Text("\(scan.scanned) / \(scan.total)").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                                }
                                ProgressView(value: Double(scan.scanned), total: Double(scan.total))
                                Text("\(pct)% durchsucht – neue Medien erscheinen laufend").font(.caption2).foregroundStyle(.secondary)
                            }
                            .padding(14)
                            .background(Color.blue.opacity(0.10), in: RoundedRectangle(cornerRadius: 16))
                        }

                        // Headline: total
                        VStack(spacing: 2) {
                            Text("\(s.total)").font(.system(size: 44, weight: .bold)).contentTransition(.numericText())
                            Text("Medien insgesamt").foregroundStyle(.secondary)
                        }.padding(.top, 8)

                        LazyVGrid(columns: cols, spacing: 12) {
                            tile("Bilder", s.images, "photo", .blue)
                            tile("Videos", s.videos, "video", .purple)
                            tile("In Verarbeitung", s.processing, "gearshape.2", .orange)
                            tile("KI-Beschreibung", s.described, "sparkles", .indigo)
                            tile("Mit Gesichtern", s.with_faces, "person.crop.square", .pink)
                            tile("Favoriten", s.favorites, "heart.fill", .red)
                            tile("Mit GPS", s.with_gps, "mappin.and.ellipse", .green)
                            tile("Beschrieben %", s.total > 0 ? Int(Double(s.described)/Double(s.total)*100) : 0, "chart.pie", .teal, suffix: "%")
                        }

                        if let span = dateSpan {
                            Text(span).font(.footnote).foregroundStyle(.secondary).padding(.top, 4)
                        }
                        if s.processing > 0 {
                            Label("\(s.processing) werden noch verarbeitet (Thumbnails sind da, KI/Gesichter laufen nach).",
                                  systemImage: "info.circle")
                                .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center)
                                .padding(.horizontal)
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("Bibliothek")
            .task { await load() }
            .refreshable { await load() }
        }
    }

    private var dateSpan: String? {
        guard let a = s?.date_min, let b = s?.date_max else { return nil }
        return "Zeitraum: \(String(a.prefix(10))) – \(String(b.prefix(10)))"
    }

    @ViewBuilder private func tile(_ label: String, _ value: Int, _ icon: String, _ color: Color, suffix: String = "") -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: icon).foregroundStyle(color)
            Text("\(value)\(suffix)").font(.title2.bold()).contentTransition(.numericText())
            Text(label).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(color.opacity(0.10), in: RoundedRectangle(cornerRadius: 16))
    }

    func load() async {
        loading = true; defer { loading = false }
        do { s = try await api.libraryStats(); loadError = nil }
        catch { loadError = (error as NSError).localizedDescription }
        // Scan progress is best-effort — never block the stats screen on it.
        scan = try? await api.scanProgress()
    }
}
