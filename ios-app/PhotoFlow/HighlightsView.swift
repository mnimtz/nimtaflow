import SwiftUI
import AVKit

/// "Highlights" video assistant — parity with the web. Lists rendered highlight
/// videos (with live polling while any are pending/rendering), plays finished
/// ones full-screen, and offers a create sheet driven by the backend mottos.
struct HighlightsView: View {
    @EnvironmentObject var api: APIClient
    @State private var items: [HighlightV1] = []
    @State private var loading = true
    @State private var error: String?
    @State private var showCreate = false
    @State private var playing: HighlightV1?
    @State private var pollTask: Task<Void, Never>?

    private let cols = [GridItem(.adaptive(minimum: 150), spacing: 12)]

    private var hasActive: Bool {
        items.contains { $0.status == "pending" || $0.status == "rendering" }
    }

    var body: some View {
        NavigationStack {
            Group {
                if loading && items.isEmpty {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let error, items.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "film").font(.largeTitle).foregroundStyle(.secondary)
                        Text(error).foregroundStyle(.secondary)
                        Button("Erneut versuchen") { Task { await load() } }
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if items.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "sparkles.tv").font(.largeTitle).foregroundStyle(.secondary)
                        Text("Noch keine Highlights").font(.headline)
                        Text("Erstelle ein Erinnerungs-Video nach Motto.")
                            .font(.subheadline).foregroundStyle(.secondary)
                        Button { showCreate = true } label: {
                            Label("Highlight erstellen", systemImage: "plus")
                        }.buttonStyle(.borderedProminent)
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        LazyVGrid(columns: cols, spacing: 12) {
                            ForEach(items) { h in
                                HighlightCard(highlight: h)
                                    .onTapGesture { if h.status == "done" { playing = h } }
                                    .contextMenu {
                                        Button(role: .destructive) {
                                            Task { await delete(h) }
                                        } label: { Label("Löschen", systemImage: "trash") }
                                    }
                            }
                        }
                        .padding(12)
                    }
                    .refreshable { await load() }
                }
            }
            .navigationTitle("Highlights")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showCreate = true } label: { Image(systemName: "plus") }
                }
            }
            .sheet(isPresented: $showCreate) {
                CreateHighlightSheet { await load() }
            }
            .fullScreenCover(item: $playing) { h in
                HighlightPlayerView(highlight: h)
            }
        }
        .task { await load(); startPolling() }
        .onDisappear { pollTask?.cancel() }
    }

    private func load() async {
        loading = items.isEmpty
        do { items = try await api.highlights(); error = nil }
        catch { self.error = "Konnte Highlights nicht laden." }
        loading = false
        startPolling()
    }

    /// Refresh on a timer while any highlight is still rendering.
    private func startPolling() {
        pollTask?.cancel()
        guard hasActive else { return }
        pollTask = Task {
            while !Task.isCancelled && hasActive {
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                if Task.isCancelled { break }
                if let fresh = try? await api.highlights() { items = fresh }
            }
        }
    }

    private func delete(_ h: HighlightV1) async {
        try? await api.deleteHighlight(h.id)
        items.removeAll { $0.id == h.id }
    }
}

private struct HighlightCard: View {
    let highlight: HighlightV1
    @EnvironmentObject var api: APIClient

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ZStack {
                if let cid = highlight.cover_photo_id {
                    Thumb(url: api.url("api/photos/\(cid)/thumbnail?size=medium"))
                } else {
                    Color.gray.opacity(0.18)
                        .overlay(Image(systemName: "film").foregroundStyle(.secondary))
                }
                if highlight.status == "done" {
                    Image(systemName: "play.circle.fill")
                        .font(.system(size: 40)).foregroundStyle(.white.opacity(0.9))
                        .shadow(radius: 4)
                }
            }
            .aspectRatio(16/9, contentMode: .fill)
            .frame(maxWidth: .infinity)
            .clipShape(RoundedRectangle(cornerRadius: 10))

            Text(highlight.title.isEmpty ? highlight.motto : highlight.title)
                .font(.subheadline).fontWeight(.semibold).lineLimit(1)
            Text("\(highlight.photo_count) Fotos · \(Int(highlight.duration_sec))s")
                .font(.caption).foregroundStyle(.secondary)
            StatusBadge(status: highlight.status, message: highlight.error_message)
        }
    }
}

private struct StatusBadge: View {
    let status: String
    let message: String?

    private var info: (String, Color)? {
        switch status {
        case "pending":   return ("Wartet…", .orange)
        case "rendering": return ("Wird erstellt…", .blue)
        case "error":     return (message ?? "Fehler", .red)
        default:          return nil   // done → no badge
        }
    }

    var body: some View {
        if let (text, color) = info {
            HStack(spacing: 4) {
                if status == "pending" || status == "rendering" {
                    ProgressView().controlSize(.mini)
                }
                Text(text).font(.caption2).lineLimit(1)
            }
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(color.opacity(0.18), in: Capsule())
            .foregroundStyle(color)
        }
    }
}

/// Full-screen player for a finished highlight. AVPlayer can't send a Bearer
/// header → auth rides along as ?access_token= (same pattern as the photo stream).
private struct HighlightPlayerView: View {
    let highlight: HighlightV1
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()
            VideoPlayerView(url: api.url("api/highlights/\(highlight.id)/video?access_token=\(api.token)"))
                .ignoresSafeArea()
            Button { dismiss() } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title).foregroundStyle(.white.opacity(0.85))
                    .padding()
            }
        }
    }
}

// MARK: - Create sheet

private struct CreateHighlightSheet: View {
    let onCreated: () async -> Void
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss

    @State private var mottos: [MottoV1] = []
    @State private var people: [PersonV1] = []
    @State private var albums: [AlbumV1] = []
    @State private var loadingOptions = true

    @State private var selectedMotto: MottoV1?
    @State private var title = ""
    @State private var duration: Double = 45
    @State private var personId: Int?
    @State private var personId2: Int?
    @State private var year = ""
    @State private var albumId: Int?
    @State private var season = "christmas"
    @State private var submitting = false
    @State private var error: String?

    private let seasons: [(String, String)] = [
        ("christmas", "Weihnachten"), ("easter", "Ostern"), ("summer", "Sommer"),
        ("winter", "Winter"), ("autumn", "Herbst"), ("halloween", "Halloween"),
    ]

    private func needs(_ p: String) -> Bool { selectedMotto?.params.contains(p) ?? false }

    var body: some View {
        NavigationStack {
            Form {
                if loadingOptions {
                    HStack { Spacer(); ProgressView(); Spacer() }
                } else {
                    Section("Motto") {
                        Picker("Motto", selection: $selectedMotto) {
                            Text("Bitte wählen").tag(MottoV1?.none)
                            ForEach(mottos) { m in
                                Text(m.label).tag(MottoV1?.some(m))
                            }
                        }
                    }

                    if selectedMotto != nil {
                        Section("Optionen") {
                            if needs("person") {
                                personPicker("Person", selection: $personId)
                            }
                            if needs("person2") {
                                personPicker("Zweite Person", selection: $personId2)
                            }
                            if needs("year") {
                                TextField("Jahr (z. B. 2024)", text: $year)
                                    .keyboardType(.numberPad)
                            }
                            if needs("album") {
                                Picker("Album", selection: $albumId) {
                                    Text("Bitte wählen").tag(Int?.none)
                                    ForEach(albums) { a in
                                        Text(a.name).tag(Int?.some(a.id))
                                    }
                                }
                            }
                            if needs("season") {
                                Picker("Anlass", selection: $season) {
                                    ForEach(seasons, id: \.0) { Text($0.1).tag($0.0) }
                                }
                            }
                            if selectedMotto?.params.isEmpty ?? true {
                                Text("Keine weiteren Angaben nötig.")
                                    .font(.subheadline).foregroundStyle(.secondary)
                            }
                        }
                    }

                    Section("Video") {
                        VStack(alignment: .leading) {
                            Text("Dauer: \(Int(duration))s")
                            Slider(value: $duration, in: 15...180, step: 5)
                        }
                        TextField("Titel (optional)", text: $title)
                    }

                    if let error {
                        Section { Text(error).foregroundStyle(.red).font(.subheadline) }
                    }

                    Section {
                        Button {
                            Task { await create() }
                        } label: {
                            HStack {
                                if submitting { ProgressView().controlSize(.small) }
                                Text("Erstellen")
                            }
                        }
                        .disabled(selectedMotto == nil || submitting)
                    }
                }
            }
            .navigationTitle("Neues Highlight")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Abbrechen") { dismiss() }
                }
            }
            .task { await loadOptions() }
        }
    }

    @ViewBuilder
    private func personPicker(_ label: String, selection: Binding<Int?>) -> some View {
        Picker(label, selection: selection) {
            Text("Bitte wählen").tag(Int?.none)
            ForEach(people) { p in
                Text(p.name).tag(Int?.some(p.id))
            }
        }
    }

    private func loadOptions() async {
        loadingOptions = true
        async let m = try? api.mottos()
        async let pp = try? api.people()
        async let aa = try? api.albums()
        mottos = await m ?? []
        people = await pp ?? []
        albums = await aa ?? []
        loadingOptions = false
    }

    private func create() async {
        guard let motto = selectedMotto else { return }
        submitting = true; error = nil
        do {
            _ = try await api.createHighlight(
                motto: motto.key,
                title: title.isEmpty ? nil : title,
                durationSec: duration,
                personId: needs("person") ? personId : nil,
                personId2: needs("person2") ? personId2 : nil,
                year: needs("year") ? Int(year) : nil,
                albumId: needs("album") ? albumId : nil,
                season: needs("season") ? season : nil
            )
            await onCreated()
            dismiss()
        } catch {
            self.error = "Erstellen fehlgeschlagen."
        }
        submitting = false
    }
}
