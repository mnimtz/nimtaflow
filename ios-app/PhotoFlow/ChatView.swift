import SwiftUI

/// Conversational assistant — same Gemini/local backend the web chat uses.
/// Each assistant turn can carry matched photo IDs, shown as a horizontal
/// thumbnail strip; tapping one opens it full-screen.
struct ChatView: View {
    @EnvironmentObject var api: APIClient
    @State private var messages: [ChatBubble] = []
    @State private var draft = ""
    @State private var sending = false
    @State private var status: ChatStatus?
    @State private var opened: PhotoV1?
    @State private var navTarget: NavTarget?
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
                                               onTapNavigate: { navTarget = NavTarget(path: $0) }).id(m.id)
                            }
                            if sending {
                                HStack(spacing: 6) { ProgressView(); Text("denkt nach…").foregroundStyle(.secondary) }
                                    .font(.footnote).padding(.horizontal)
                            }
                        }
                        .padding(.vertical, 12)
                    }
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: messages.count) { _, _ in
                        if let last = messages.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
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
            }
            .task { status = try? await api.chatStatus() }
            .fullScreenCover(item: $opened) { p in PhotoPager(photos: [p], start: p) }
            .sheet(item: $navTarget) { t in
                navDestination(t.path)
                    .presentationDetents([.large]).presentationDragIndicator(.visible)
            }
        }
    }

    func open(_ id: Int) { Task { opened = try? await api.photo(id) } }

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
        let hist = messages.dropLast().map { ChatTurn(role: $0.role, content: $0.text) }
        do {
            let reply = try await api.chat(message: text, history: Array(hist))
            messages.append(ChatBubble(role: "assistant", text: reply.answer, photoIDs: reply.photo_ids,
                                       suggestions: reply.suggestions ?? [], navigate: reply.navigate))
        } catch {
            messages.append(ChatBubble(role: "assistant", text: "⚠️ Konnte gerade nicht antworten. Bitte nochmal.", photoIDs: []))
        }
    }
}

struct ChatBubble: Identifiable, Hashable {
    let id = UUID()
    let role: String       // "user" | "assistant"
    let text: String
    let photoIDs: [Int]
    var suggestions: [String] = []
    var navigate: String? = nil   // Ansichts-Navigation (z. B. "/people?person=3")
}

/// Wrapper, damit ein Navigations-Pfad als .sheet(item:) präsentierbar ist.
struct NavTarget: Identifiable { let id = UUID(); let path: String }

private struct ChatBubbleView: View {
    @EnvironmentObject var api: APIClient
    let bubble: ChatBubble
    let onTapPhoto: (Int) -> Void
    var onTapSuggestion: (String) -> Void = { _ in }
    var onTapNavigate: (String) -> Void = { _ in }
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
                            Thumb(url: api.url("api/photos/\(pid)/thumbnail?size=medium"))
                                .frame(width: 92, height: 92)
                                .clipShape(RoundedRectangle(cornerRadius: 10))
                                .onTapGesture { onTapPhoto(pid) }
                        }
                    }
                    .padding(.horizontal, 2)
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
