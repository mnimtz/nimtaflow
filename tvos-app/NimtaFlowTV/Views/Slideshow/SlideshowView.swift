import SwiftUI

struct SlideshowView: View {
    let api: APIClient

    @State private var photos: [PhotoV1] = []
    @State private var isLoading = true
    @State private var currentIndex = 0
    @State private var isPaused = false
    @State private var showControls = false
    @State private var speedIndex = 1
    @State private var controlsHideTask: Task<Void, Never>? = nil

    private let speeds = [3.0, 5.0, 10.0, 20.0]
    private var interval: Double { speeds[speedIndex] }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if isLoading {
                VStack(spacing: 16) {
                    ProgressView()
                    Text("Lade Fotos…").foregroundStyle(.secondary)
                }
            } else if photos.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "photo.slash").font(.system(size: 60)).foregroundStyle(.secondary)
                    Text("Keine Fotos für Diashow").foregroundStyle(.secondary)
                }
            } else {
                photoView
                if showControls { controlsOverlay }
            }
        }
        .task { await loadPhotos() }
        // Auto-advance timer: restarts when index, pause state, or speed changes
        .task(id: "\(currentIndex)-\(isPaused)-\(speedIndex)") {
            guard !isPaused, !photos.isEmpty else { return }
            try? await Task.sleep(for: .seconds(interval))
            guard !isPaused else { return }
            withAnimation(.easeInOut(duration: 0.8)) {
                currentIndex = (currentIndex + 1) % photos.count
            }
        }
        .onMoveCommand(perform: handleMove)
        .onPlayPauseCommand {
            isPaused.toggle()
            showControlsBriefly()
        }
    }

    private var photoView: some View {
        let photo = photos[currentIndex]
        return AuthAsyncImage(
            url: api.fixedURL(photo.original_url),
            headers: api.authHeaders()
        ) { image in
            image.resizable().aspectRatio(contentMode: .fit)
        } placeholder: {
            // Show thumbnail while full-res loads
            AuthAsyncImage(url: api.fixedURL(photo.thumb_medium_url), headers: api.authHeaders()) { img in
                img.resizable().aspectRatio(contentMode: .fit).blur(radius: 2)
            } placeholder: { Color.clear }
        }
        .id(currentIndex)
        .transition(.opacity)
        .ignoresSafeArea()
    }

    private var controlsOverlay: some View {
        VStack {
            Spacer()
            HStack(spacing: 32) {
                Label(isPaused ? "Pausiert" : "Läuft",
                      systemImage: isPaused ? "pause.fill" : "play.fill")

                Divider().frame(height: 20)

                Label("\(Int(interval))s", systemImage: "clock")

                Divider().frame(height: 20)

                Text("\(currentIndex + 1) / \(photos.count)")
                    .foregroundStyle(.secondary)
            }
            .font(.body)
            .padding(.horizontal, 24)
            .padding(.vertical, 14)
            .background(.black.opacity(0.75), in: Capsule())
            .padding(.bottom, 60)
        }
        .transition(.opacity)
    }

    private func handleMove(_ dir: MoveCommandDirection) {
        switch dir {
        case .left:
            currentIndex = (currentIndex - 1 + photos.count) % photos.count
        case .right:
            currentIndex = (currentIndex + 1) % photos.count
        case .up:
            speedIndex = (speedIndex + 1) % speeds.count
        case .down:
            speedIndex = (speedIndex - 1 + speeds.count) % speeds.count
        default:
            break
        }
        showControlsBriefly()
    }

    private func showControlsBriefly() {
        withAnimation { showControls = true }
        controlsHideTask?.cancel()
        controlsHideTask = Task {
            try? await Task.sleep(for: .seconds(4))
            if !Task.isCancelled {
                withAnimation { showControls = false }
            }
        }
    }

    private func loadPhotos() async {
        var all: [PhotoV1] = []
        var cursor: Int? = nil
        repeat {
            guard let page = try? await api.fetchPhotos(cursor: cursor, limit: 60) else { break }
            all += page.items.filter { !$0.is_video }
            cursor = page.next_cursor
            if all.count >= 400 { break }
        } while cursor != nil
        photos = all.shuffled()
        isLoading = false
    }
}
