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
                                ChatBubbleView(bubble: m, onTapPhoto: { open($0) }).id(m.id)
                            }
                            if sending {
                                HStack(spacing: 6) { ProgressView(); Text("denkt nach…").foregroundStyle(.secondary) }
                                    .font(.footnote).padding(.horizontal)
                            }
                        }
                        .padding(.vertical, 12)
                    }
                    .onChange(of: messages.count) { _, _ in
                        if let last = messages.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
                    }
                }
                Divider()
                HStack(spacing: 8) {
                    TextField("Frag etwas über deine Fotos…", text: $draft, axis: .vertical)
                        .textFieldStyle(.roundedBorder).lineLimit(1...4)
                        .onSubmit { Task { await sendIt() } }
                    Button { Task { await sendIt() } } label: {
                        Image(systemName: "arrow.up.circle.fill").font(.title2)
                    }
                    .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty || sending)
                }
                .padding(10)
            }
            .navigationTitle("Chat")
            .task { status = try? await api.chatStatus() }
            .fullScreenCover(item: $opened) { p in PhotoPager(photos: [p], start: p) }
        }
    }

    func open(_ id: Int) { Task { opened = try? await api.photo(id) } }

    func sendIt() async {
        let text = draft.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty, !sending else { return }
        draft = ""
        messages.append(ChatBubble(role: "user", text: text, photoIDs: []))
        sending = true; defer { sending = false }
        let hist = messages.dropLast().map { ChatTurn(role: $0.role, content: $0.text) }
        do {
            let reply = try await api.chat(message: text, history: Array(hist))
            messages.append(ChatBubble(role: "assistant", text: reply.answer, photoIDs: reply.photo_ids))
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
}

private struct ChatBubbleView: View {
    @EnvironmentObject var api: APIClient
    let bubble: ChatBubble
    let onTapPhoto: (Int) -> Void
    var isUser: Bool { bubble.role == "user" }

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
