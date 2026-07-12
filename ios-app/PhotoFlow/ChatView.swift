import SwiftUI

/// Conversational assistant — same Gemini/local backend the web chat uses.
/// Each assistant turn can carry matched photo IDs, shown as a horizontal
/// thumbnail strip; tapping one opens it full-screen.
struct ChatView: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var dismiss
    @State private var messages: [ChatBubble] = []
    @State private var draft = ""
    @State private var sending = false
    @State private var status: ChatStatus?
    @State private var opened: PhotoV1?
    @State private var navTarget: NavTarget?
    @State private var gallery: GalleryPresentation?
    @State private var loadingGallery = false
    @FocusState private var inputFocused: Bool

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            if messages.isEmpty {
                                ChatHint(status: status)
                            }
                            ForEach(messages) { m in
                                ChatBubbleView(bubble: m, onTapPhoto: { open($0) },
                                               onTapSuggestion: { s in Task { await sendIt(preset: s) } },
                                               onTapNavigate: { navTarget = NavTarget(path: $0) },
                                               onOpenGallery: { ids in Task { await openGallery(ids) } },
                                               onOpenInGallery: { ids in sendToGallery(ids) }).id(m.id)
                            }
                            if sending {
                                HStack(spacing: 6) { ProgressView(); Text("denkt nach…").foregroundStyle(.secondary) }
                                    .font(.footnote).padding(.horizontal)
                            }
                            if loadingGallery {
                                HStack(spacing: 6) { ProgressView(); Text("Galerie öffnen…").foregroundStyle(.secondary) }
                                    .font(.footnote).padding(.horizontal)
                            }
                        }
                        .padding(.vertical, 12)
                    }
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: messages.count) { _, _ in
                        if let last = messages.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
                    }
                    .onChange(of: inputFocused) { _, focused in
                        // Beim Tastatur-Öffnen die letzte Nachricht wieder sichtbar
                        // machen — sonst verschwindet sie hinter dem Keyboard.
                        if focused, let last = messages.last {
                            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                        }
                    }
                }
                Divider()
                HStack(spacing: 8) {
                    TextField("Frag etwas über deine Fotos…", text: $draft, axis: .vertical)
                        .textFieldStyle(.roundedBorder).lineLimit(1...4)
                        .focused($inputFocused)
                        .onSubmit { Task { await sendIt() } }
                    Button { Task { await sendIt() } } label: {
                        Image(systemName: "arrow.up.circle.fill").font(.title2)
                    }
                    .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty || sending)
                }
                .padding(10)
            }
            .navigationTitle("Chat")
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Fertig") { inputFocused = false }
                }
                // Schließen-Button ganz links — sonst kam man aus dem Sheet mit
                // offener Tastatur nicht mehr raus („man kommt nicht raus").
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        inputFocused = false
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title3)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .task { status = try? await api.chatStatus() }
            .fullScreenCover(item: $opened) { p in PhotoPager(photos: [p], start: p) }
            .fullScreenCover(item: $gallery) { g in
                if let first = g.photos.first { PhotoPager(photos: g.photos, start: first) }
            }
            .sheet(item: $navTarget) { t in
                navDestination(t.path)
                    .presentationDetents([.large]).presentationDragIndicator(.visible)
            }
        }
    }

    func open(_ id: Int) {
        Task {
            do { opened = try await api.photo(id) }
            catch { messages.append(ChatBubble(role: "assistant",
                        text: "Konnte das Foto nicht öffnen.", photoIDs: [], isError: true)) }
        }
    }

    /// Öffnet ALLE Treffer-IDs als Vollbild-Swipe-Galerie im Chat.
    func openGallery(_ ids: [Int]) async {
        guard !ids.isEmpty, !loadingGallery else { return }
        loadingGallery = true; defer { loadingGallery = false }
        do {
            let photos = try await api.photosByIDs(ids)
            if !photos.isEmpty { gallery = GalleryPresentation(photos: photos) }
        } catch {
            messages.append(ChatBubble(role: "assistant",
                text: "Konnte die Galerie gerade nicht öffnen.", photoIDs: [], isError: true))
        }
    }

    /// Filtert die Galerie auf diese IDs und schließt den Chat-Sheet.
    /// Vorher-Bug: `store.chatGalleryFilter = ids` allein reichte nicht, wenn der
    /// User auf einem anderen Tab (Dashboard/Alben/Mehr) war — GalleryView war
    /// gar nicht gemountet, `onChange` griff nie. Fix: zusätzlich zum Galerie-
    /// Tab wechseln, DANN Filter setzen (kleine Verzögerung damit die View
    /// wirklich montiert ist bevor der onChange feuert).
    func sendToGallery(_ ids: [Int]) {
        guard !ids.isEmpty else { return }
        store.selectedTab = 1
        // Kleine Verzögerung: TabView braucht einen Frame um die neue View zu mounten,
        // sonst kann der onChange-Handler den Filter verpassen (Timing-Race).
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [store] in
            store.chatGalleryFilter = ids
        }
        dismiss()
    }

    /// Phase 1: verarbeitet strukturierte Intents aus der Backend-Antwort.
    /// Leitet filter_map direkt an den Store weiter; filter_gallery wird über
    /// result_ids abgedeckt (die bestehende ID-basierte Filterung reicht für Phase 1).
    func applyIntents(_ payloads: [AssistantIntentPayload]) {
        for payload in payloads {
            guard let intent = AssistantIntent.from(payload) else { continue }
            switch intent {
            case .filterMap(let personId, let dateFrom, let dateTo):
                let filter = AssistantMapFilter(personId: personId, dateFrom: dateFrom, dateTo: dateTo)
                if !filter.isEmpty {
                    store.chatMapFilter = filter
                }
            case .filterGallery:
                // Galerie-Filter läuft bereits via result_ids → store.chatGalleryFilter.
                // Keine zusätzliche Aktion nötig (ID-basiert reicht für Phase 1).
                break
            case .navigate:
                // navigate kommt bereits als reply.navigate String → wird separat behandelt.
                break
            }
        }
    }

    /// Person-ID aus einem Pfad wie "/people?person=3" ziehen (für Deep-Select).
    private func personId(from path: String) -> Int? {
        URLComponents(string: "http://x" + path)?.queryItems?
            .first(where: { $0.name == "person" })?.value.flatMap { Int($0) }
    }

    /// Bildet den Web-Pfad des Assistenten auf die passende iOS-Ansicht ab.
    @ViewBuilder func navDestination(_ path: String) -> some View {
        if path.hasPrefix("/people") { PeopleView(initialPersonId: personId(from: path)) }
        else if path.hasPrefix("/albums") { AlbumsView() }
        else if path.hasPrefix("/trips") { TripsView() }
        else if path.hasPrefix("/map") { MapScreen() }
        else if path.hasPrefix("/highlights") { HighlightsView() }
        else if path.hasPrefix("/relationships") { RelationshipsView() }
        else if path.hasPrefix("/leitstand") { LeitstandView() }
        else if path.hasPrefix("/search") { SearchView() }
        else { GalleryView() }
    }

    func sendIt(preset: String? = nil) async {
        let text = (preset ?? draft).trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty, !sending else { return }
        if preset == nil { draft = "" }
        messages.append(ChatBubble(role: "user", text: text, photoIDs: []))
        sending = true; defer { sending = false }
        // Fehler-Bubbles NICHT in die History geben — sonst bekäme das Modell
        // „Konnte nicht antworten" als echten Assistent-Turn in den Kontext.
        let hist = messages.dropLast().filter { !$0.isError }
            .map { ChatTurn(role: $0.role, content: $0.text) }
        // context_ids: letzte Assistenten-Antwort mit Treffern → für Folgefragen ("davon", "daraus")
        let lastResultIDs = messages.last(where: { $0.role == "assistant" && !$0.resultIDs.isEmpty })?.resultIDs ?? []
        do {
            let reply = try await api.chat(message: text, history: Array(hist), contextIDs: lastResultIDs)
            // Teaser-Strip: zitierte Fotos, sonst die ersten paar Treffer. Das VOLLE
            // Set (resultIDs) hängt an der Bubble → „In Galerie öffnen" zeigt alle.
            let full = reply.result_ids ?? reply.photo_ids
            let shown = !reply.photo_ids.isEmpty ? Array(reply.photo_ids.prefix(4))
                                                 : Array(full.prefix(4))
            var seen = Set<String>()
            let sugg = (reply.suggestions ?? [])
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty && seen.insert($0.lowercased()).inserted }
            messages.append(ChatBubble(role: "assistant", text: reply.answer, photoIDs: shown,
                                       resultIDs: full,
                                       suggestions: sugg, navigate: reply.navigate))
            // Phase 1: strukturierte Intents verarbeiten
            applyIntents(reply.intents ?? [])
        } catch APIClient.APIError.status(401) {
            messages.append(ChatBubble(role: "assistant",
                text: "Deine Sitzung ist abgelaufen. Bitte melde dich neu an.", photoIDs: [], isError: true))
        } catch {
            messages.append(ChatBubble(role: "assistant",
                text: "⚠️ Konnte gerade nicht antworten. Bitte nochmal.", photoIDs: [], isError: true))
        }
    }
}

/// Wrapper, damit eine geladene Trefferliste als .fullScreenCover(item:) präsentierbar ist.
struct GalleryPresentation: Identifiable { let id = UUID(); let photos: [PhotoV1] }

struct ChatBubble: Identifiable, Hashable {
    let id = UUID()
    let role: String       // "user" | "assistant"
    let text: String
    let photoIDs: [Int]           // Teaser-Thumbnails (max. ~4)
    var resultIDs: [Int] = []     // VOLLES Treffer-Set → "In Galerie öffnen"
    var suggestions: [String] = []
    var navigate: String? = nil   // Ansichts-Navigation (z. B. "/people?person=3")
    var isError: Bool = false     // Fehler-Bubble → nicht in die History geben
}

/// Wrapper, damit ein Navigations-Pfad als .sheet(item:) präsentierbar ist.
struct NavTarget: Identifiable { let id = UUID(); let path: String }

private struct ChatBubbleView: View {
    @EnvironmentObject var api: APIClient
    let bubble: ChatBubble
    let onTapPhoto: (Int) -> Void
    var onTapSuggestion: (String) -> Void = { _ in }
    var onTapNavigate: (String) -> Void = { _ in }
    var onOpenGallery: ([Int]) -> Void = { _ in }
    var onOpenInGallery: ([Int]) -> Void = { _ in }  // schließt Sheet + filtert Galerie-Tab
    var isUser: Bool { bubble.role == "user" }

    private func navLabel(_ path: String) -> String {
        if path.hasPrefix("/people") { return "Personen öffnen" }
        if path.hasPrefix("/albums") { return "Alben öffnen" }
        if path.hasPrefix("/trips") { return "Reisen öffnen" }
        if path.hasPrefix("/map") { return "Karte öffnen" }
        if path.hasPrefix("/highlights") { return "Highlights öffnen" }
        if path.hasPrefix("/relationships") { return "Beziehungen öffnen" }
        if path.hasPrefix("/leitstand") { return "Leitstand öffnen" }
        if path.hasPrefix("/search") { return "Suche öffnen" }
        return "Galerie öffnen"
    }

    var body: some View {
        VStack(alignment: isUser ? .trailing : .leading, spacing: 6) {
            Text(bubble.text)
                .padding(10)
                .background(isUser ? Color.indigo : Color.gray.opacity(0.2),
                            in: RoundedRectangle(cornerRadius: 14))
                .foregroundStyle(isUser ? .white : .primary)
                .frame(maxWidth: 300, alignment: isUser ? .trailing : .leading)
            if !bubble.photoIDs.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(bubble.photoIDs, id: \.self) { pid in
                            Thumb(url: api.url("api/photos/\(pid)/thumbnail?size=small"))
                                .frame(width: 92, height: 92)
                                .clipShape(RoundedRectangle(cornerRadius: 10))
                                .onTapGesture { onTapPhoto(pid) }
                        }
                    }
                    .padding(.horizontal, 2)
                }
            }
            // Treffer gehören in die GALERIE: zwei Wege —
            // 1. "In Galerie öffnen" → filtert den Galerie-Tab und schließt den Chat-Sheet.
            // 2. "Als Vollbild ansehen" → öffnet PhotoPager direkt im Chat (für schnellen Blick).
            if !bubble.resultIDs.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    Button { onOpenInGallery(bubble.resultIDs) } label: {
                        Label(bubble.resultIDs.count > 1
                              ? "Alle \(bubble.resultIDs.count) in Galerie öffnen"
                              : "In Galerie öffnen",
                              systemImage: "rectangle.grid.2x2")
                            .font(.footnote.weight(.medium))
                            .padding(.horizontal, 12).padding(.vertical, 7)
                            .background(Color.indigo.opacity(0.18), in: Capsule())
                            .foregroundStyle(.indigo)
                    }
                    Button { onOpenGallery(bubble.resultIDs) } label: {
                        Label("Als Vollbild ansehen", systemImage: "photo.on.rectangle.angled")
                            .font(.footnote.weight(.medium))
                            .padding(.horizontal, 12).padding(.vertical, 7)
                            .background(Color.secondary.opacity(0.12), in: Capsule())
                            .foregroundStyle(.secondary)
                    }
                }
            }
            // Ansichts-Navigation ("öffne Anjas Seite", "zeig die Reisen")
            if let nav = bubble.navigate, !nav.isEmpty {
                Button { onTapNavigate(nav) } label: {
                    Label(navLabel(nav), systemImage: "arrow.up.forward.app")
                        .font(.footnote.weight(.medium))
                        .padding(.horizontal, 12).padding(.vertical, 7)
                        .background(Color.indigo.opacity(0.18), in: Capsule())
                        .foregroundStyle(.indigo)
                }
            }
            // Proaktive Folge-Vorschläge als antippbare Chips
            if !bubble.suggestions.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(bubble.suggestions, id: \.self) { s in
                            Button { onTapSuggestion(s) } label: {
                                Text(s).font(.footnote)
                                    .padding(.horizontal, 12).padding(.vertical, 7)
                                    .background(Color.indigo.opacity(0.15), in: Capsule())
                                    .foregroundStyle(.indigo)
                            }
                        }
                    }
                    .padding(.horizontal, 2)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
        .padding(.horizontal, 12)
    }
}

private struct ChatHint: View {
    let status: ChatStatus?
    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "bubble.left.and.text.bubble.right").font(.largeTitle).foregroundStyle(.indigo)
            Text("Frag nach deinen Fotos").font(.headline)
            Text(verbatim: "„Zeig mir Strandfotos von Lea letztes Jahr\u{201C}")
                .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
            if let s = status, s.provider == "gemini", !s.gemini_ready {
                Text("⚠️ Kein Gemini-Key hinterlegt (Einstellungen → KI).")
                    .font(.caption).foregroundStyle(.orange)
            }
        }
        .frame(maxWidth: .infinity).padding(.top, 50).padding(.horizontal)
    }
}
