import SwiftUI

/// "Bibliothek" — the at-a-glance totals: how many images vs videos the scan
/// found, how much is still processing, AI/faces coverage, and the date span.
struct LibraryStatsView: View {
    @EnvironmentObject var api: APIClient
    @State private var s: LibraryStats?
    @State private var loading = false

    private let cols = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        NavigationStack {
            ScrollView {
                if loading && s == nil { ProgressView().padding(.top, 60) }
                if let s {
                    VStack(spacing: 16) {
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
        s = try? await api.libraryStats()
    }
}
