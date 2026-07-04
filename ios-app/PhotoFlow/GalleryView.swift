import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import AVKit
import AVFoundation

struct GalleryView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var store: Store
    @State private var photos: [PhotoV1] = []
    @State private var cursor: Int? = nil
    @State private var hasMore = true
    @State private var loading = false
    @State private var favoritesOnly = false
    @State private var selected: PhotoV1?
    @State private var loadError: String?
    @State private var lastTotal: Int?
    // Filter / sort
    @State private var sort = "newest"
    @State private var mediaType: String? = nil
    @State private var personId: Int? = nil
    @State private var personName: String? = nil
    @State private var showFilter = false
    // Chat-Assistent → Galerie-Filter (wenn Nutzer "In Galerie öffnen" im Chat tippt)
    @State private var chatFilteredPhotos: [PhotoV1]? = nil
    @State private var chatFilterLoading = false
    private var filterActive: Bool { mediaType != nil || personId != nil || sort != "newest" }

    // Upload
    @State private var pickerItems: [PhotosPickerItem] = []
    @State private var uploading = false
    @State private var uploadDone = 0
    @State private var uploadTotal = 0
    @State private var uploadNote: String?
    @AppStorage("gallery_group") private var groupMode = "day"   // none|day|month|year (default: Tag)
    @AppStorage("gallery_layout") private var layoutMode = "grid" // grid|justified|masonry
    @AppStorage("gallery_timeline") private var showTimeline = true

    // Multi-Select
    @State private var selectionMode = false
    @State private var selectedIDs: Set<Int> = []
    @State private var bulkBusy = false
    @State private var showBulkDeleteConfirm = false

    // Timeline scrubber
    @State private var scrubProxy: ScrollViewProxy? = nil
    @State private var timelineBuckets: [APIClient.TimelineBucket] = []
    @State private var jumpDateFrom: String? = nil
    @State private var jumpDateTo: String? = nil

    let cols = [GridItem(.adaptive(minimum: 110), spacing: 2)]
    private let groupOpts: [(String, String)] = [
        ("none", "Keine Gruppierung"), ("day", "Nach Tag"), ("month", "Nach Monat"), ("year", "Nach Jahr"),
    ]
    private let layoutOpts: [(String, String, String)] = [
        ("grid", "Raster", "square.grid.2x2"),
        ("justified", "Justified", "rectangle.grid.1x2"),
        ("masonry", "Masonry", "rectangle.grid.3x2"),
    ]

    private var sections: [(key: String, items: [PhotoV1])] {
        if groupMode == "none" { return [("", displayPhotos)] }
        var order: [String] = []; var map: [String: [PhotoV1]] = [:]
        for p in displayPhotos {
            let k = groupKey(p.taken_at)
            if map[k] == nil { map[k] = []; order.append(k) }
            map[k]!.append(p)
        }
        return order.map { (key: $0, items: map[$0]!) }
    }
    private func groupKey(_ iso: String?) -> String {
        guard let iso, iso.count >= 7 else { return "—" }
        switch groupMode {
        case "day": return String(iso.prefix(10))
        case "month": return String(iso.prefix(7))
        case "year": return String(iso.prefix(4))
        default: return ""
        }
    }
    private func groupLabel(_ key: String) -> String {
        if key == "—" { return "Ohne Datum" }
        let f = DateFormatter(); f.locale = Locale(identifier: "de_DE")
        let o = DateFormatter(); o.locale = Locale(identifier: "de_DE")
        switch groupMode {
        case "day":   f.dateFormat = "yyyy-MM-dd"; o.dateFormat = "EEEE, d. MMMM yyyy"
        case "month": f.dateFormat = "yyyy-MM";    o.dateFormat = "LLLL yyyy"
        default:      return key   // year
        }
        return f.date(from: key).map { o.string(from: $0) } ?? key
    }

    private var displayPhotos: [PhotoV1] { chatFilteredPhotos ?? photos }

    var body: some View {
        NavigationStack {
            ZStack(alignment: .trailing) {
                ScrollViewReader { proxy in
                    ScrollView {
                        Color.clear.frame(height: 0).id("__gallery_top__")
                        // Chat-Filter-Banner
                        if chatFilteredPhotos != nil {
                            HStack(spacing: 8) {
                                if chatFilterLoading {
                                    ProgressView().scaleEffect(0.8)
                                } else {
                                    Image(systemName: "sparkles").foregroundStyle(.indigo)
                                    Text("\(chatFilteredPhotos?.count ?? 0) Treffer vom Assistenten")
                                        .font(.footnote.weight(.medium))
                                }
                                Spacer()
                                Button { chatFilteredPhotos = nil; store.chatGalleryFilter = nil } label: {
                                    Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                                }
                            }
                            .padding(.horizontal, 12).padding(.vertical, 8)
                            .background(Color.indigo.opacity(0.08))
                        }
                        LazyVStack(alignment: .leading, spacing: 2,
                                   pinnedViews: groupMode == "none" ? [] : [.sectionHeaders]) {
                            ForEach(sections, id: \.key) { sec in
                                Section {
                                    sectionBody(sec.items)
                                } header: {
                                    if !sec.key.isEmpty {
                                        Text(groupLabel(sec.key))
                                            .font(.subheadline.weight(.semibold))
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                            .padding(.horizontal, 10).padding(.vertical, 6)
                                            .background(.ultraThinMaterial)
                                            .id(sec.key)
                                    }
                                }
                            }
                        }
                        .padding(2)
                        if loading || chatFilterLoading { ProgressView().padding() }
                        if !loading && !chatFilterLoading && displayPhotos.isEmpty { emptyState }
                    }
                    .onAppear { scrubProxy = proxy }
                }
                // Zeitleisten-Scrubber (rechter Rand)
                if showTimeline && !timelineBuckets.isEmpty {
                    TimelineScrubber(buckets: timelineBuckets) { year in
                        Task { await jumpToYear(year) }
                    }
                }
            }
            .navigationTitle(selectionMode ? "\(selectedIDs.count) ausgewählt" : "Galerie")
            .toolbar {
                if selectionMode {
                    ToolbarItem(placement: .topBarLeading) {
                        Button("Abbrechen") { selectionMode = false; selectedIDs = [] }
                    }
                } else {
                    ToolbarItem(placement: .topBarLeading) {
                        Menu {
                            Picker("Gruppierung", selection: $groupMode) {
                                ForEach(groupOpts, id: \.0) { Text($0.1).tag($0.0) }
                            }
                        } label: { Image(systemName: "calendar") }
                    }
                    ToolbarItem(placement: .topBarLeading) {
                        Menu {
                            Picker("Layout", selection: $layoutMode) {
                                ForEach(layoutOpts, id: \.0) { opt in
                                    Label(opt.1, systemImage: opt.2).tag(opt.0)
                                }
                            }
                            Divider()
                            Toggle(isOn: Binding(
                                get: { showTimeline },
                                set: { v in
                                    showTimeline = v
                                    if v && timelineBuckets.isEmpty { Task { await loadTimelineBuckets() } }
                                }
                            )) { Label("Zeitleiste", systemImage: "timeline.selection") }
                        } label: {
                            Image(systemName: layoutOpts.first { $0.0 == layoutMode }?.2 ?? "square.grid.2x2")
                        }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        PhotosPicker(selection: $pickerItems, maxSelectionCount: nil,
                                     matching: .any(of: [.images, .videos])) {
                            Image(systemName: "plus.circle")
                        }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { favoritesOnly.toggle(); Task { await reload() } } label: {
                            Image(systemName: favoritesOnly ? "heart.fill" : "heart")
                        }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { showFilter = true } label: {
                            Image(systemName: filterActive ? "line.3.horizontal.decrease.circle.fill"
                                                            : "line.3.horizontal.decrease.circle")
                        }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { selectionMode = true } label: {
                            Image(systemName: "checkmark.circle")
                        }
                    }
                }
            }
            .sheet(isPresented: $showFilter) {
                GalleryFilterSheet(sort: $sort, mediaType: $mediaType, personId: $personId,
                                   personName: $personName, onApply: { Task { await reload() } })
            }
            .overlay(alignment: .bottom) {
                // Upload-Banner
                if uploading || uploadNote != nil {
                    HStack(spacing: 10) {
                        if uploading { ProgressView() }
                        Text(uploadNote ?? "Lade hoch… \(uploadDone)/\(uploadTotal)")
                            .font(.footnote)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .background(.ultraThinMaterial, in: Capsule())
                    .padding(.bottom, 16)
                }
                // Bulk-Aktionen-Leiste
                if selectionMode && !selectedIDs.isEmpty {
                    HStack(spacing: 0) {
                        if bulkBusy {
                            ProgressView().frame(maxWidth: .infinity)
                        } else {
                            Button {
                                Task { await bulkArchive() }
                            } label: {
                                Label("Archivieren", systemImage: "archivebox")
                                    .frame(maxWidth: .infinity)
                            }
                            Divider().frame(height: 28)
                            Button(role: .destructive) {
                                showBulkDeleteConfirm = true
                            } label: {
                                Label("Löschen", systemImage: "trash")
                                    .frame(maxWidth: .infinity)
                            }
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12)
                    .background(.ultraThinMaterial)
                    .confirmationDialog("\(selectedIDs.count) Fotos endgültig löschen?",
                                       isPresented: $showBulkDeleteConfirm,
                                       titleVisibility: .visible) {
                        Button("Löschen", role: .destructive) { Task { await bulkDelete() } }
                    }
                }
            }
            .onChange(of: pickerItems) { _, items in
                if !items.isEmpty { Task { await upload(items) } }
            }
            .refreshable { await reload() }
            .task {
                if photos.isEmpty { await load() }
                if showTimeline && timelineBuckets.isEmpty { await loadTimelineBuckets() }
            }
            .onChange(of: showTimeline) { _, v in
                if v && timelineBuckets.isEmpty { Task { await loadTimelineBuckets() } }
            }
            .onChange(of: store.chatGalleryFilter) { _, ids in
                guard let ids, !ids.isEmpty else { chatFilteredPhotos = nil; return }
                Task { await applyChatFilter(ids) }
            }
            .fullScreenCover(item: $selected) { p in
                PhotoPager(photos: displayPhotos, start: p,
                           onRemoved: { id in
                               if chatFilteredPhotos != nil {
                                   chatFilteredPhotos?.removeAll { $0.id == id }
                               } else {
                                   photos.removeAll { $0.id == id }
                               }
                           })
            }
        }
    }

    // MARK: - Section layout dispatch

    @ViewBuilder private func sectionBody(_ items: [PhotoV1]) -> some View {
        let tapHandler: (PhotoV1) -> Void = selectionMode
            ? { p in
                if selectedIDs.contains(p.id) { selectedIDs.remove(p.id) }
                else { selectedIDs.insert(p.id) }
            }
            : { p in selected = p }

        switch layoutMode {
        case "masonry":
            MasonrySection(items: items, onTap: tapHandler, onLast: { onAppearLast($0) },
                           selectionMode: selectionMode, selectedIDs: selectedIDs)
                .onLongPressGesture { if !selectionMode { selectionMode = true } }
        case "justified":
            JustifiedSection(items: items, onTap: tapHandler, onLast: { onAppearLast($0) },
                             selectionMode: selectionMode, selectedIDs: selectedIDs)
                .onLongPressGesture { if !selectionMode { selectionMode = true } }
        default:
            LazyVGrid(columns: cols, spacing: 2) {
                ForEach(items) { p in
                    PhotoTile(photo: p)
                        .overlay(alignment: .topLeading) {
                            if selectionMode {
                                SelectionBadge(selected: selectedIDs.contains(p.id)).padding(4)
                            }
                        }
                        .onTapGesture {
                            if selectionMode {
                                if selectedIDs.contains(p.id) { selectedIDs.remove(p.id) }
                                else { selectedIDs.insert(p.id) }
                            } else { selected = p }
                        }
                        .onLongPressGesture {
                            if !selectionMode { selectionMode = true; selectedIDs.insert(p.id) }
                        }
                        .onAppear { onAppearLast(p) }
                }
            }
        }
    }

    // MARK: - Bulk actions

    private func bulkArchive() async {
        bulkBusy = true
        defer { bulkBusy = false }
        let ids = Array(selectedIDs)
        for id in ids {
            try? await api.archivePhoto(id)
        }
        if chatFilteredPhotos != nil {
            chatFilteredPhotos?.removeAll { ids.contains($0.id) }
        } else {
            photos.removeAll { ids.contains($0.id) }
        }
        selectedIDs = []; selectionMode = false
    }

    private func bulkDelete() async {
        bulkBusy = true
        defer { bulkBusy = false }
        let ids = Array(selectedIDs)
        for id in ids {
            try? await api.deletePhoto(id)
        }
        if chatFilteredPhotos != nil {
            chatFilteredPhotos?.removeAll { ids.contains($0.id) }
        } else {
            photos.removeAll { ids.contains($0.id) }
        }
        selectedIDs = []; selectionMode = false
    }

    private func onAppearLast(_ p: PhotoV1) {
        if p.id == displayPhotos.last?.id && chatFilteredPhotos == nil { Task { await load() } }
    }

    func upload(_ items: [PhotosPickerItem]) async {
        uploading = true; uploadDone = 0; uploadTotal = items.count; uploadNote = nil
        var ok = 0, dup = 0, fail = 0
        for item in items {
            defer { uploadDone += 1 }
            guard let data = try? await item.loadTransferable(type: Data.self) else { fail += 1; continue }
            let ut = item.supportedContentTypes.first
            let ext = ut?.preferredFilenameExtension ?? "jpg"
            let mime = ut?.preferredMIMEType ?? "image/jpeg"
            let name = "upload_\(UUID().uuidString.prefix(8)).\(ext)"
            do {
                let r = try await api.uploadFile(data: data, filename: name, mime: mime)
                if r.status == "duplicate" { dup += 1 } else if r.status == "accepted" { ok += 1 } else { fail += 1 }
            } catch { fail += 1 }
        }
        pickerItems = []
        uploading = false
        var msg = "\(ok) hochgeladen"
        if dup > 0 { msg += ", \(dup) Duplikate" }
        if fail > 0 { msg += ", \(fail) fehlgeschlagen" }
        uploadNote = msg + " · wird verarbeitet…"
        await reload()
        try? await Task.sleep(nanoseconds: 4_000_000_000)
        uploadNote = nil
    }

    @ViewBuilder private var emptyState: some View {
        VStack(spacing: 10) {
            if chatFilteredPhotos != nil {
                Image(systemName: "sparkles").font(.largeTitle).foregroundStyle(.indigo)
                Text("Keine Treffer für diesen Chat-Filter").font(.headline)
                Button("Filter zurücksetzen") { chatFilteredPhotos = nil; store.chatGalleryFilter = nil }
                    .buttonStyle(.borderedProminent).padding(.top, 4)
            } else {
                Image(systemName: loadError == nil ? "photo.on.rectangle" : "exclamationmark.triangle")
                    .font(.largeTitle).foregroundStyle(loadError == nil ? Color.secondary : Color.orange)
                Text(loadError ?? "Keine Fotos geladen").font(.headline).multilineTextAlignment(.center)
                if let t = lastTotal { Text("Server meldet \(t) Fotos").font(.caption).foregroundStyle(.secondary) }
                Text("Server: \(api.serverURL)").font(.caption2).foregroundStyle(.secondary)
                Button("Erneut laden") { Task { await reload() } }
                    .buttonStyle(.borderedProminent).padding(.top, 4)
            }
        }
        .frame(maxWidth: .infinity).padding(.top, 80).padding(.horizontal)
    }

    // Refresh: fetch the first page fresh and REPLACE only on success (no wiping
    // the grid first — avoids the flash + a cancelled refresh keeping old photos).
    func reload() async {
        guard !loading else { return }
        jumpDateFrom = nil; jumpDateTo = nil
        loading = true; defer { loading = false }
        do {
            // The first page MUST carry the same filters as load(); otherwise an
            // active sort / media-type / person / favourites filter is ignored for
            // page 1 and only kicks in on scroll → a visibly jumbled grid.
            let page = try await api.photos(cursor: nil, favorites: favoritesOnly,
                                            mediaType: mediaType, sort: sort, personId: personId)
            photos = page.items; cursor = page.next_cursor; hasMore = page.has_more
            lastTotal = page.total; loadError = nil
        } catch { handle(error) }
    }

    func load() async {
        guard hasMore, !loading else { return }
        loading = true; defer { loading = false }
        do {
            let page: PhotoPage
            if let from = jumpDateFrom, let to = jumpDateTo {
                page = try await api.photosByDate(from: from, to: to, cursor: cursor,
                                                  favorites: favoritesOnly, mediaType: mediaType,
                                                  sort: sort, personId: personId)
            } else {
                page = try await api.photos(cursor: cursor, favorites: favoritesOnly,
                                            mediaType: mediaType, sort: sort, personId: personId)
            }
            photos += page.items; cursor = page.next_cursor; hasMore = page.has_more
            lastTotal = page.total; loadError = nil
        } catch { handle(error) }
    }

    private func loadTimelineBuckets() async {
        guard let buckets = try? await api.timelineBuckets() else { return }
        timelineBuckets = buckets
    }

    private func jumpToYear(_ year: Int) async {
        guard !loading else { return }
        let from = "\(year)-01-01"
        let to   = "\(year)-12-31"
        jumpDateFrom = from; jumpDateTo = to
        loading = true; defer { loading = false }
        do {
            let page = try await api.photosByDate(from: from, to: to, cursor: nil,
                                                  favorites: favoritesOnly, mediaType: mediaType,
                                                  sort: sort, personId: personId)
            photos = page.items; cursor = page.next_cursor; hasMore = page.has_more
            lastTotal = page.total; loadError = nil
            withAnimation { scrubProxy?.scrollTo("__gallery_top__", anchor: .top) }
        } catch { handle(error) }
    }

    /// Lädt Fotos für die IDs aus dem Chat-Assistenten und zeigt sie gefiltert in der Galerie.
    func applyChatFilter(_ ids: [Int]) async {
        guard !ids.isEmpty else { chatFilteredPhotos = nil; return }
        chatFilterLoading = true; defer { chatFilterLoading = false }
        do {
            let fetched = try await api.photosByIDs(ids)
            chatFilteredPhotos = fetched
        } catch {
            chatFilteredPhotos = nil
            store.chatGalleryFilter = nil
        }
    }

    private func handle(_ error: Error) {
        // A cancelled request (pull-to-refresh released, view changed) is NOT a
        // real failure — ignore it silently and allow another attempt.
        if error is CancellationError { return }
        if let u = error as? URLError, u.code == .cancelled { return }
        hasMore = false
        if let e = error as? APIClient.APIError {
            switch e {
            case .status(let c): loadError = "Server antwortet mit Fehler \(c)"
            case .decode(let underlying): loadError = "Antwort nicht lesbar (Decode-Fehler: \(underlying.localizedDescription))"
            case .badURL: loadError = "Server-Adresse ungültig"
            }
        } else {
            loadError = "Verbindung fehlgeschlagen: \((error as NSError).localizedDescription)"
        }
    }
}

// MARK: - Variable-size photo cell (for masonry & justified)

// MARK: - Selection badge

struct SelectionBadge: View {
    let selected: Bool
    var body: some View {
        ZStack {
            Circle()
                .fill(selected ? Color.indigo : Color.black.opacity(0.35))
                .frame(width: 22, height: 22)
            if selected {
                Image(systemName: "checkmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.white)
            } else {
                Circle().stroke(Color.white, lineWidth: 1.5).frame(width: 20, height: 20)
            }
        }
    }
}

// MARK: - Timeline scrubber

struct TimelineScrubber: View {
    let buckets: [APIClient.TimelineBucket]
    let onJump: (Int) -> Void

    @State private var isDragging = false
    @State private var dragY: CGFloat = 0
    @State private var dragYear: Int = 0

    private var total: Int { buckets.reduce(0) { $0 + $1.count } }

    // One entry per unique year: (year, cumulative-count BEFORE this year)
    private var yearMarkers: [(year: Int, cumBefore: Int)] {
        var result: [(Int, Int)] = []
        var seen = Set<Int>()
        var cum = 0
        for b in buckets {
            if let yr = Int(b.month.prefix(4)), !seen.contains(yr) {
                seen.insert(yr); result.append((yr, cum))
            }
            cum += b.count
        }
        return result
    }

    private func yearAt(progress: CGFloat) -> Int {
        let target = Int(progress * CGFloat(total))
        var cum = 0
        for b in buckets {
            cum += b.count
            if cum > target, let yr = Int(b.month.prefix(4)) { return yr }
        }
        return yearMarkers.last?.0 ?? 0
    }

    var body: some View {
        GeometryReader { geo in
            let h = geo.size.height
            let t = max(1, total)

            ZStack(alignment: .trailing) {
                // Track
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(Color.white.opacity(isDragging ? 0.6 : 0.3))
                    .frame(width: 3, height: h)

                // Year tick + label
                ForEach(yearMarkers, id: \.0) { yr, cum in
                    let yPos = CGFloat(cum) / CGFloat(t) * h
                    HStack(spacing: 4) {
                        Text(String(yr))
                            .font(.system(size: 9, weight: .semibold, design: .rounded))
                            .foregroundStyle(.white)
                            .shadow(color: .black.opacity(0.8), radius: 1)
                        Rectangle()
                            .fill(Color.white.opacity(0.65))
                            .frame(width: 5, height: 1.5)
                    }
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .offset(y: yPos - h / 2)
                }

                // Floating year bubble while dragging
                if isDragging {
                    Text(String(dragYear))
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 14).padding(.vertical, 8)
                        .background(Color.indigo.opacity(0.92), in: Capsule())
                        .shadow(color: .black.opacity(0.3), radius: 4, y: 2)
                        .offset(x: -50, y: dragY - h / 2)
                }
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { val in
                        isDragging = true
                        dragY = max(0, min(h, val.location.y))
                        let yr = yearAt(progress: dragY / h)
                        if yr != dragYear {
                            dragYear = yr
                            onJump(yr)
                        }
                    }
                    .onEnded { _ in isDragging = false }
            )
        }
        .frame(width: 48)
    }
}

/// A photo cell that fills the size it is given (no forced square), reusing the
/// same image loader + play/favorite badges as `PhotoTile`. Tapping opens the pager.
struct VarPhotoCell: View {
    @EnvironmentObject var api: APIClient
    let photo: PhotoV1
    let width: CGFloat
    let height: CGFloat
    let onTap: () -> Void

    var body: some View {
        Thumb(url: api.url("api/photos/\(photo.id)/thumbnail?size=medium"))
            .frame(width: width, height: height)
            .clipped()
            .overlay(alignment: .bottomLeading) {
                if photo.is_video {
                    Image(systemName: "play.fill").font(.caption2).foregroundStyle(.white)
                        .padding(4).shadow(radius: 2)
                }
            }
            .overlay(alignment: .topTrailing) {
                if photo.is_favorite {
                    Image(systemName: "heart.fill").font(.caption2).foregroundStyle(.red).padding(4)
                }
            }
            .contentShape(Rectangle())
            .onTapGesture(perform: onTap)
    }
}

private func clampedAspect(_ p: PhotoV1) -> Double {
    // aspect = width / height. Guard against nil/0/extreme panoramas.
    let a = p.aspect_ratio ?? 0
    if a > 0.01 { return min(max(a, 0.4), 3.0) }
    if let w = p.width, let h = p.height, h > 0 { return min(max(Double(w) / Double(h), 0.4), 3.0) }
    return 1.0
}

// MARK: - Masonry (Pinterest-style columns)

/// Splits the section's photos into N columns (2 compact / 3 regular) and renders
/// each column as a VStack of variable-height cells. Items are placed into the
/// currently shortest column for a balanced layout. Packing is computed once per
/// width from the photo list (no per-frame recompute).
struct MasonrySection: View {
    let items: [PhotoV1]
    let onTap: (PhotoV1) -> Void
    let onLast: (PhotoV1) -> Void
    var selectionMode: Bool = false
    var selectedIDs: Set<Int> = []
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var containerWidth: CGFloat = UIScreen.main.bounds.width

    var body: some View {
        GeometryReader { geo in
            let spacing: CGFloat = 2
            let colCount = (sizeClass == .compact) ? 2 : 3
            let colWidth = (geo.size.width - spacing * CGFloat(colCount - 1)) / CGFloat(colCount)
            let columns = pack(into: colCount, colWidth: colWidth)
            HStack(alignment: .top, spacing: spacing) {
                ForEach(0..<colCount, id: \.self) { ci in
                    VStack(spacing: spacing) {
                        ForEach(columns[ci]) { p in
                            VarPhotoCell(photo: p, width: colWidth,
                                         height: colWidth / CGFloat(clampedAspect(p)),
                                         onTap: { onTap(p) })
                                .overlay(alignment: .topLeading) {
                                    if selectionMode {
                                        SelectionBadge(selected: selectedIDs.contains(p.id)).padding(4)
                                    }
                                }
                                .onAppear { onLast(p) }
                        }
                    }
                }
            }
        }
        .frame(height: totalHeight(width: containerWidth))
        .background(GeometryReader { geo in
            Color.clear.onAppear { containerWidth = geo.size.width }
        })
    }

    private func pack(into colCount: Int, colWidth: CGFloat) -> [[PhotoV1]] {
        var cols = Array(repeating: [PhotoV1](), count: colCount)
        var heights = Array(repeating: CGFloat(0), count: colCount)
        for p in items {
            let i = heights.firstIndex(of: heights.min()!) ?? 0
            cols[i].append(p)
            heights[i] += colWidth / CGFloat(clampedAspect(p)) + 2
        }
        return cols
    }

    // Approximate total height so GeometryReader gets a real height inside LazyVStack.
    private func totalHeight(width: CGFloat) -> CGFloat {
        let colCount = (sizeClass == .compact) ? 2 : 3
        let spacing: CGFloat = 2
        let colWidth = (width - spacing * CGFloat(colCount - 1)) / CGFloat(colCount)
        var heights = Array(repeating: CGFloat(0), count: colCount)
        for p in items {
            let i = heights.firstIndex(of: heights.min()!) ?? 0
            heights[i] += colWidth / CGFloat(clampedAspect(p)) + spacing
        }
        return (heights.max() ?? 0)
    }
}

// MARK: - Justified (Google-Photos style rows)

/// Greedily packs photos into rows scaled to fill the container width at a target
/// row height, keeping each item's aspect ratio. Packing is computed once per
/// width from the photo list.
struct JustifiedSection: View {
    let items: [PhotoV1]
    let onTap: (PhotoV1) -> Void
    let onLast: (PhotoV1) -> Void
    var selectionMode: Bool = false
    var selectedIDs: Set<Int> = []
    @State private var containerWidth: CGFloat = UIScreen.main.bounds.width

    private let targetH: CGFloat = 140
    private let spacing: CGFloat = 2

    var body: some View {
        GeometryReader { geo in
            let rows = buildRows(width: geo.size.width)
            VStack(spacing: spacing) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    HStack(spacing: spacing) {
                        ForEach(row.items) { p in
                            VarPhotoCell(photo: p,
                                         width: CGFloat(clampedAspect(p)) * row.height,
                                         height: row.height,
                                         onTap: { onTap(p) })
                                .overlay(alignment: .topLeading) {
                                    if selectionMode {
                                        SelectionBadge(selected: selectedIDs.contains(p.id)).padding(4)
                                    }
                                }
                                .onAppear { onLast(p) }
                        }
                    }
                }
            }
        }
        .frame(height: totalHeight())
        .background(GeometryReader { geo in
            Color.clear.onAppear { containerWidth = geo.size.width }
        })
    }

    private struct Row { var items: [PhotoV1]; var height: CGFloat }

    private func buildRows(width: CGFloat) -> [Row] {
        guard width > 1 else { return [] }
        var rows: [Row] = []
        var cur: [PhotoV1] = []
        var sumAspect: Double = 0
        for p in items {
            cur.append(p)
            sumAspect += clampedAspect(p)
            // gaps between items at target height
            let gaps = Double(cur.count - 1) * Double(spacing)
            let projectedWidth = sumAspect * Double(targetH) + gaps
            if projectedWidth >= Double(width) {
                let avail = Double(width) - gaps
                let h = CGFloat(avail / sumAspect)
                rows.append(Row(items: cur, height: min(h, targetH * 1.6)))
                cur = []; sumAspect = 0
            }
        }
        if !cur.isEmpty {
            // last partial row keeps target height (don't stretch a lonely image)
            rows.append(Row(items: cur, height: targetH))
        }
        return rows
    }

    private func totalHeight() -> CGFloat {
        let rows = buildRows(width: containerWidth)
        return rows.reduce(0) { $0 + $1.height + spacing }
    }
}

/// Full-screen swipeable, zoomable photo viewer.
struct PhotoPager: View {
    @EnvironmentObject var api: APIClient
    let photos: [PhotoV1]
    let start: PhotoV1
    var onRemoved: ((Int) -> Void)? = nil   // tell the grid to drop a trashed/deleted photo
    @Environment(\.dismiss) var dismiss
    @State private var index: Int = 0
    @State private var favs: Set<Int> = []
    @State private var ratings: [Int: Int] = [:]
    @State private var actionNote: String?
    @State private var showShare = false
    @State private var showInfo = false
    @State private var showAlbumPicker = false
    @State private var showDeleteConfirm = false
    @State private var profileFaces: [PhotoFace] = []
    @State private var showProfileDialog = false
    @State private var showAnimate = false

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()
            TabView(selection: $index) {
                ForEach(Array(photos.enumerated()), id: \.element.id) { i, p in
                    Group {
                        if p.is_video {
                            // v1 stream = proper HTTP Range for AVPlayer; auth via
                            // ?access_token= since AVPlayer can't send a Bearer header.
                            VideoPlayerView(url: api.url("api/v1/photos/\(p.id)/stream?access_token=\(api.token)"))
                        } else {
                            // Large thumbnail (always JPEG) — works for RAW too, where the
                            // original isn't displayable by iOS.
                            ZoomableImage(url: api.url("api/photos/\(p.id)/thumbnail?size=large"))
                        }
                    }.tag(i)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            HStack(spacing: 18) {
                Button { Task { guard let p = cur else { return }; try? await api.toggleFavorite(p.id); toggleLocal() } } label: {
                    Image(systemName: isFav ? "heart.fill" : "heart").foregroundStyle(isFav ? .red : .white)
                }
                Button { showInfo = true } label: { Image(systemName: "info.circle").foregroundStyle(.white) }
                Menu {
                    Button { showShare = true } label: { Label("Teilen", systemImage: "square.and.arrow.up") }
                    Button { showAlbumPicker = true } label: { Label("Zu Album hinzufügen", systemImage: "rectangle.stack.badge.plus") }
                    if let c = cur, !c.is_video {
                        Button { showAnimate = true } label: { Label("Animieren / KI-Szene", systemImage: "sparkles") }
                    }
                    Button { Task { await loadProfileFaces() } } label: { Label("Als Personen-Titelbild", systemImage: "person.crop.circle.badge.checkmark") }
                    Button { Task { guard let p = cur else { return }; try? await api.archivePhoto(p.id); actionNote = "Archiviert" } } label: {
                        Label("Archivieren", systemImage: "archivebox")
                    }
                    Button { Task { guard let p = cur else { return }; try? await api.reprocess(p.id); actionNote = "Wird neu verarbeitet…" } } label: {
                        Label("Neu verarbeiten", systemImage: "arrow.triangle.2.circlepath")
                    }
                    Button(role: .destructive) {
                        guard let id = cur?.id else { return }
                        Task { try? await api.trashPhoto(id); onRemoved?(id); dismiss() }
                    } label: { Label("In Papierkorb", systemImage: "trash") }
                    Button(role: .destructive) { showDeleteConfirm = true } label: {
                        Label("Endgültig löschen", systemImage: "trash.slash")
                    }
                } label: { Image(systemName: "ellipsis.circle.fill").foregroundStyle(.white) }
                .sheet(isPresented: $showAnimate) {
                    AnimateSceneSheet(isPresented: $showAnimate, photoId: cur?.id ?? 0) { actionNote = "Animation gestartet — erscheint unter Highlights." }
                        .presentationDetents([.medium, .large])
                }
                Button { dismiss() } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(.white) }
            }
            .font(.title2).padding()

            // Rating stars — bottom centre, write straight through to the server.
            VStack {
                Spacer()
                HStack(spacing: 6) {
                    ForEach(1...5, id: \.self) { star in
                        Image(systemName: star <= curRating ? "star.fill" : "star")
                            .foregroundStyle(star <= curRating ? .yellow : .white.opacity(0.6))
                            .onTapGesture {
                                guard let id = cur?.id else { return }
                                let newVal = (curRating == star) ? 0 : star   // tap same star clears
                                ratings[id] = newVal
                                Task { try? await api.setRating(id, rating: newVal) }
                            }
                    }
                }
                .font(.title3).padding(8)
                .background(.black.opacity(0.35), in: Capsule()).padding(.bottom, 28)
                .overlay(alignment: .top) {
                    if let actionNote { Text(actionNote).font(.caption).foregroundStyle(.white).offset(y: -22) }
                }
            }
        }
        .onAppear {
            index = photos.firstIndex(of: start) ?? 0
            favs = Set(photos.filter { $0.is_favorite }.map { $0.id })
            ratings = Dictionary(uniqueKeysWithValues: photos.map { ($0.id, $0.user_rating ?? 0) })
            prefetchNeighbors()
        }
        .onChange(of: index) { _, _ in actionNote = nil; prefetchNeighbors() }
        .sheet(isPresented: $showShare) {
            if let c = cur {
                ShareSheetView(target: .photo(id: c.id, title: c.filename))
                    .presentationDetents([.medium])
            }
        }
        .sheet(isPresented: $showInfo) {
            if let p = photos[safe: index] { PhotoInfoView(photo: p).presentationDetents([.medium, .large]) }
        }
        .sheet(isPresented: $showAlbumPicker) {
            AlbumPickerSheet { albumId in
                guard let id = cur?.id else { return }
                Task { try? await api.addPhotosToAlbum(albumId, photoIds: [id]); actionNote = "Zu Album hinzugefügt" }
            }.presentationDetents([.medium, .large])
        }
        .confirmationDialog("Als Titelbild setzen für…", isPresented: $showProfileDialog, titleVisibility: .visible) {
            ForEach(profileFaces) { f in
                Button(f.person_name) {
                    Task { try? await api.setProfileFace(personId: f.person_id, faceId: f.face_id)
                           actionNote = "Titelbild gesetzt: \(f.person_name)" }
                }
            }
            Button("Abbrechen", role: .cancel) {}
        }
        .confirmationDialog("Dieses Medium endgültig löschen? Datei und Eintrag werden entfernt – das kann nicht rückgängig gemacht werden.",
                            isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("Endgültig löschen", role: .destructive) {
                guard let id = cur?.id else { return }
                Task { try? await api.deletePhoto(id); onRemoved?(id); dismiss() }
            }
            Button("Abbrechen", role: .cancel) {}
        }
    }

    func loadProfileFaces() async {
        let faces = (try? await api.photoFaces(photos[index].id)) ?? []
        if faces.isEmpty { actionNote = "Keine erkannte Person im Bild" }
        else { profileFaces = faces; showProfileDialog = true }
    }

    /// The currently shown photo, bounds-safe — `photos` can shrink under the open
    /// pager (trash/delete → parent removes the item), so never index it raw at
    /// render time.
    var cur: PhotoV1? { photos[safe: index] }
    var isFav: Bool { favs.contains(photos[safe: index]?.id ?? -1) }

    /// Warm the large image of the previous/next photo so swiping is instant.
    private func prefetchNeighbors() {
        for off in [-1, 1] {
            let i = index + off
            guard photos.indices.contains(i) else { continue }
            let p = photos[i]
            if !p.is_video {
                prefetchImage(api.url("api/photos/\(p.id)/thumbnail?size=large"), token: api.token)
            }
        }
    }
    var curRating: Int { ratings[photos[safe: index]?.id ?? -1] ?? 0 }
    func toggleLocal() { guard let id = cur?.id else { return }; if favs.contains(id) { favs.remove(id) } else { favs.insert(id) } }
}

struct ZoomableImage: View {
    let url: URL?
    @State private var scale: CGFloat = 1
    var body: some View {
        Thumb(url: url)
            .aspectRatio(contentMode: .fit)
            .scaleEffect(scale)
            .gesture(MagnificationGesture().onChanged { scale = max(1, $0) }.onEnded { _ in withAnimation { scale = max(1, min(scale, 4)) } })
            .onTapGesture(count: 2) { withAnimation { scale = scale > 1 ? 1 : 2.5 } }
    }
}

extension Array { subscript(safe i: Int) -> Element? { indices.contains(i) ? self[i] : nil } }

/// Streams a video. The stream endpoint needs auth, and AVPlayer can't send a
/// Bearer header on its own → the URL already carries the token as a
/// `?access_token=` query param (built by the caller), which the backend's
/// auth guard accepts. So a plain AVPlayer(url:) is all that's needed here.
struct VideoPlayerView: View {
    let url: URL?              // already carries ?access_token= for auth
    @State private var player: AVPlayer?

    var body: some View {
        Group {
            if let player {
                VideoPlayer(player: player)
                    .onAppear {
                        // Play audio even when the ring/silent switch is on — without
                        // this AVPlayer uses the default (soloAmbient) session and stays
                        // muted on silent, so highlight music + video sound were silent.
                        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
                        try? AVAudioSession.sharedInstance().setActive(true)
                        player.play()
                    }
                    .onDisappear {
                        player.pause()
                        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
                    }
            } else {
                Color.black.overlay(ProgressView().tint(.white))
            }
        }
        .task(id: url) {
            guard let url else { return }
            player = AVPlayer(url: url)
        }
    }
}

/// Read-only metadata for a photo/video — date, resolution, place, people, tags,
/// description, camera/EXIF, GPS. Loads the full /detail payload on appear.
struct PhotoInfoView: View {
    let photo: PhotoV1
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss
    @State private var detail: PhotoDetailV1?
    @State private var askQ = ""
    @State private var askAnswer = ""
    @State private var askBusy = false
    @State private var askProvider = "local"
    @State private var postcardURL: URL?
    @State private var pcBusy = false
    @State private var pcTheme = "classic"
    @State private var pcColor = ""   // "" = Standard, sonst #rrggbb
    @State private var allPeople: [PersonV1] = []

    private func reassignFace(_ faceId: Int, to personId: Int) async {
        try? await api.assignFace(faceId, to: personId)
        detail = try? await api.photoDetail(photo.id)
    }
    private func removeFace(_ faceId: Int) async {
        try? await api.unassignFace(faceId)
        detail = try? await api.photoDetail(photo.id)
    }

    /// Alter der Person zum Aufnahmezeitpunkt, falls Geburtsdatum + Foto-Datum bekannt.
    private func ageAtPhoto(_ birthdate: String?) -> Int? {
        guard let bds = birthdate, let shot = detail?.taken_at ?? photo.taken_at else { return nil }
        let iso = ISO8601DateFormatter()
        let day = DateFormatter(); day.dateFormat = "yyyy-MM-dd"; day.timeZone = TimeZone(identifier: "UTC")
        guard let bd = day.date(from: String(bds.prefix(10))),
              let sd = (iso.date(from: shot) ?? day.date(from: String(shot.prefix(10)))) else { return nil }
        let yrs = Calendar.current.dateComponents([.year], from: bd, to: sd).year ?? -1
        return (yrs >= 0 && yrs < 130) ? yrs : nil
    }

    private func makePostcard() async {
        pcBusy = true; defer { pcBusy = false }
        var path = "api/v1/photos/\(photo.id)/postcard?theme=\(pcTheme)"
        if !pcColor.isEmpty {
            path += "&text_color=" + (pcColor.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? "")
        }
        if let data = try? await api.getData(path) {
            let u = FileManager.default.temporaryDirectory.appendingPathComponent("nimtaflow-postkarte-\(photo.id).png")
            try? data.write(to: u); postcardURL = u
        }
    }

    private func runAsk() async {
        askBusy = true; defer { askBusy = false }
        askAnswer = ""
        do {
            let r = try await api.askPhoto(photo.id, question: askQ, provider: askProvider)
            askAnswer = r.answer.isEmpty ? (r.error.map { "(\($0))" } ?? "Keine Antwort.") : r.answer
        } catch { askAnswer = "Fehler bei der Anfrage." }
    }

    private var dateStr: String {
        guard let t = photo.taken_at else { return "—" }
        let iso = ISO8601DateFormatter()
        guard let d = iso.date(from: t) ?? ISO8601DateFormatter().date(from: String(t.prefix(19)) + "Z") else { return t }
        let o = DateFormatter(); o.locale = Locale(identifier: "de_DE"); o.dateStyle = .long; o.timeStyle = .short
        return o.string(from: d)
    }
    private var placeStr: String? {
        let parts = [detail?.location_name, detail?.city, detail?.country].compactMap { $0 }.filter { !$0.isEmpty }
        var seen = Set<String>(); let uniq = parts.filter { seen.insert($0).inserted }
        return uniq.isEmpty ? nil : uniq.joined(separator: ", ")
    }
    private var cameraStr: String? {
        let c = [detail?.camera_make, detail?.camera_model].compactMap { $0 }.filter { !$0.isEmpty }
        return c.isEmpty ? nil : c.joined(separator: " ")
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    row("Dateiname", photo.filename)
                    row("Typ", photo.is_video ? "Video" : "Foto")
                    row("Aufgenommen", dateStr)
                    if let w = photo.width, let h = photo.height { row("Auflösung", "\(w) × \(h)") }
                    if let d = photo.duration_seconds, photo.is_video {
                        row("Dauer", String(format: "%d:%02d", Int(d) / 60, Int(d) % 60))
                    }
                    if let fs = detail?.file_size, fs > 0 {
                        row("Größe", ByteCountFormatter.string(fromByteCount: Int64(fs), countStyle: .file))
                    }
                    if let r = photo.user_rating, r > 0 { row("Bewertung", String(repeating: "★", count: r)) }
                    row("Favorit", photo.is_favorite ? "Ja" : "Nein")
                }
                if let desc = detail?.description, !desc.isEmpty {
                    Section("Beschreibung") { Text(desc).font(.callout) }
                }
                if let people = detail?.people, !people.isEmpty {
                    Section("Personen") {
                        ForEach(people) { pp in
                            HStack {
                                Image(systemName: "person.crop.circle").foregroundStyle(.indigo)
                                Text(pp.name)
                                if let age = ageAtPhoto(pp.birthdate) {
                                    Text("· \(age) J.").font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if let fid = pp.face_id {
                                    Menu {
                                        Menu("Ändern zu …") {
                                            ForEach(allPeople.filter { !$0.name.isEmpty && $0.id != pp.person_id }) { cand in
                                                Button(cand.name) { Task { await reassignFace(fid, to: cand.id) } }
                                            }
                                        }
                                        Button(role: .destructive) { Task { await removeFace(fid) } } label: {
                                            Label("Entfernen", systemImage: "person.badge.minus")
                                        }
                                    } label: { Image(systemName: "ellipsis.circle").foregroundStyle(.secondary) }
                                }
                            }
                        }
                    }
                }
                if let tags = detail?.tags, !tags.isEmpty {
                    Section("Tags") { Text(tags.joined(separator: ", ")).font(.callout).foregroundStyle(.secondary) }
                }
                if !photo.is_video {
                    Section("🖼️ Postkarte") {
                        Picker("Layout", selection: $pcTheme) {
                            Text("Klassisch").tag("classic"); Text("Modern").tag("modern")
                            Text("Polaroid").tag("polaroid"); Text("Kino").tag("film")
                            Text("Vintage").tag("vintage")
                        }
                        Picker("Schriftfarbe", selection: $pcColor) {
                            Text("Standard").tag(""); Text("Weiß").tag("#ffffff")
                            Text("Schwarz").tag("#1c1a18"); Text("Gold").tag("#e8b54a")
                        }
                        Button {
                            Task { await makePostcard() }
                        } label: {
                            HStack {
                                if pcBusy { ProgressView().controlSize(.small) }
                                Text("Postkarte erstellen")
                            }
                        }.disabled(pcBusy)
                        if let u = postcardURL {
                            ShareLink(item: u) { Label("Postkarte teilen", systemImage: "square.and.arrow.up") }
                        }
                    }
                    Section("💬 Frag-das-Foto") {
                        TextField("z. B. Wo wurde das aufgenommen?", text: $askQ)
                            .autocorrectionDisabled()
                        Picker("Modell", selection: $askProvider) {
                            Text("Lokal (privat)").tag("local")
                            Text("Cloud (Foto wird gesendet)").tag("gemini")
                        }
                        Button {
                            Task { await runAsk() }
                        } label: {
                            HStack {
                                if askBusy { ProgressView().controlSize(.small) }
                                Text("Fragen")
                            }
                        }.disabled(askBusy || askQ.trimmingCharacters(in: .whitespaces).isEmpty)
                        if !askAnswer.isEmpty { Text(askAnswer).font(.callout) }
                    }
                }
                if let d = detail {
                    VoiceMemoSection(photoId: photo.id, hasNote: d.has_voice_note ?? false)
                }
                Section("Ort & Aufnahme") {
                    if let p = placeStr { row("Ort", p) }
                    if let lat = photo.latitude, let lng = photo.longitude {
                        row("GPS", String(format: "%.5f, %.5f", lat, lng))
                    }
                    if let c = cameraStr { row("Kamera", c) }
                    if let l = detail?.lens_model, !l.isEmpty { row("Objektiv", l) }
                    if let f = detail?.focal_length { row("Brennweite", String(format: "%.0f mm", f)) }
                    if let a = detail?.aperture { row("Blende", String(format: "ƒ/%.1f", a)) }
                    if let s = detail?.shutter_speed, !s.isEmpty { row("Belichtung", s) }
                    if let i = detail?.iso { row("ISO", "\(i)") }
                }
            }
            .navigationTitle("Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Fertig") { dismiss() } } }
            .task {
                detail = try? await api.photoDetail(photo.id)
                if allPeople.isEmpty { allPeople = (try? await api.people()) ?? [] }
            }
        }
    }

    @ViewBuilder private func row(_ k: String, _ v: String) -> some View {
        HStack { Text(k).foregroundStyle(.secondary); Spacer(); Text(v).multilineTextAlignment(.trailing) }
    }
}

/// Pick an album to add a photo to (or create a new one).
struct AlbumPickerSheet: View {
    let onPick: (Int) -> Void
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss
    @State private var albums: [AlbumV1] = []
    @State private var showCreate = false
    @State private var newName = ""

    var body: some View {
        NavigationStack {
            List {
                ForEach(albums) { a in
                    Button { onPick(a.id); dismiss() } label: {
                        HStack {
                            Image(systemName: "rectangle.stack").foregroundStyle(.indigo)
                            Text(a.name); Spacer()
                            Text("\(a.photo_count)").foregroundStyle(.secondary).font(.caption)
                        }
                    }.foregroundStyle(.primary)
                }
            }
            .navigationTitle("Zu Album hinzufügen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Abbrechen") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) { Button { newName = ""; showCreate = true } label: { Image(systemName: "plus") } }
            }
            .alert("Neues Album", isPresented: $showCreate) {
                TextField("Name", text: $newName)
                Button("Erstellen & hinzufügen") {
                    let n = newName.trimmingCharacters(in: .whitespaces)
                    if !n.isEmpty { Task {
                        try? await api.createAlbum(name: n)
                        albums = (try? await api.albums()) ?? []
                        if let created = albums.first(where: { $0.name == n }) { onPick(created.id); dismiss() }
                    } }
                }
                Button("Abbrechen", role: .cancel) {}
            }
            .task { albums = (try? await api.albums()) ?? [] }
        }
    }
}

/// KI-Szene: animate one photo (optional creative scene prompt) via the chosen provider.
struct AnimateSceneSheet: View {
    @EnvironmentObject var api: APIClient
    @Binding var isPresented: Bool          // control the sheet directly (reliable close)
    let photoId: Int
    var onStarted: () -> Void
    @State private var prompt = ""
    @State private var submitting = false
    @State private var error: String?

    private let presets: [(String, String)] = [
        ("🎬 Dezente Bewegung", ""),
        ("🌊 Unterwasserwelt", "Diese Person schwimmt langsam durch eine leuchtende Unterwasserwelt mit bunten Fischen und Korallen, sanfte Lichtstrahlen."),
        ("🚀 Weltraum", "Diese Person schwebt durch den Weltraum zwischen Sternen, Planeten und farbigen Nebeln, cinematische langsame Bewegung."),
        ("❄️ Winterwunderland", "Diese Person geht durch einen verschneiten Märchenwald mit funkelndem Schnee und Polarlichtern."),
        ("🧚 Märchenwald", "Diese Person läuft durch einen magischen, leuchtenden Märchenwald voller Glühwürmchen."),
        ("☁️ Über den Wolken", "Diese Person fliegt sanft über goldene Wolken bei Sonnenuntergang."),
        ("🌆 Cyberpunk-Stadt", "Diese Person geht durch eine neonbeleuchtete Cyberpunk-Stadt bei Nacht, Regen, Spiegelungen."),
    ]

    var body: some View {
        NavigationStack {
            Form {
                Section("Szene wählen") {
                    ForEach(presets, id: \.0) { p in
                        Button(p.0) { prompt = p.1 }
                    }
                }
                Section("Beschreibung (optional)") {
                    TextField("z. B. Diese Person läuft durch eine Unterwasserwelt …", text: $prompt, axis: .vertical)
                        .lineLimit(2...5)
                }
                Section {
                    Text("Bei wilden Szenen kann die Ähnlichkeit der Person leiden. Kostet je nach Anbieter (Einstellungen → Highlights) und muss dort aktiviert sein.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let error { Section { Text(error).foregroundStyle(.red).font(.subheadline) } }
                Section {
                    Button {
                        Task {
                            submitting = true; error = nil
                            do {
                                try await api.animatePhoto(photoId, prompt: prompt.isEmpty ? nil : prompt)
                                onStarted(); isPresented = false
                            } catch { self.error = "Start fehlgeschlagen — ist KI-Video aktiviert?" }
                            submitting = false
                        }
                    } label: {
                        HStack { if submitting { ProgressView().controlSize(.small) }; Text("Animieren") }
                    }.disabled(submitting)
                }
            }
            .navigationTitle("Foto animieren")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button("Abbrechen") { isPresented = false } } }
        }
    }
}
