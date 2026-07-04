import SwiftUI
import AVKit

struct MediaPlayerView: View {
    let initialPhoto: PhotoV1
    let photos: [PhotoV1]
    let api: APIClient

    @Environment(\.dismiss) private var dismiss

    @State private var currentIndex: Int
    @State private var isFavorite: Bool
    @State private var showInfo = false
    @State private var infoHideTask: Task<Void, Never>? = nil
    @State private var player: AVPlayer? = nil

    init(photo: PhotoV1, photos: [PhotoV1], api: APIClient) {
        self.initialPhoto = photo
        self.photos = photos
        self.api = api
        let idx = photos.firstIndex(where: { $0.id == photo.id }) ?? 0
        _currentIndex = State(initialValue: idx)
        _isFavorite = State(initialValue: photo.is_favorite)
    }

    private var current: PhotoV1 { photos.isEmpty ? initialPhoto : photos[currentIndex] }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            mediaContent
            if showInfo { infoOverlay }
        }
        .onMoveCommand(perform: handleMove)
        .onPlayPauseCommand { toggleInfo() }
        .onExitCommand { dismiss() }
        .onChange(of: currentIndex) { _ in updatePlayer() }
        .onAppear { updatePlayer() }
    }

    // MARK: Media

    @ViewBuilder
    private var mediaContent: some View {
        if current.is_video {
            if let p = player {
                VideoPlayer(player: p)
                    .ignoresSafeArea()
                    .onDisappear { p.pause() }
            } else {
                ProgressView()
            }
        } else {
            AuthAsyncImage(
                url: api.fixedURL(current.original_url),
                headers: api.authHeaders()
            ) { image in
                image.resizable().aspectRatio(contentMode: .fit)
            } placeholder: {
                ProgressView()
            }
            .ignoresSafeArea()
        }
    }

    // MARK: Info overlay

    private var infoOverlay: some View {
        VStack {
            Spacer()
            HStack(alignment: .bottom) {
                VStack(alignment: .leading, spacing: 8) {
                    if let loc = current.location_name {
                        Label(loc, systemImage: "mappin.and.ellipse")
                            .font(.headline)
                    }
                    Text(DateUtils.displayDate(current.taken_at))
                        .font(.title3)
                    if let w = current.width, let h = current.height {
                        Text("\(w) × \(h) px")
                            .foregroundStyle(.secondary)
                    }
                    if current.is_video, let dur = current.duration_seconds {
                        Label(DateUtils.duration(dur), systemImage: "clock")
                            .foregroundStyle(.secondary)
                    }
                    Text("\(currentIndex + 1) / \(photos.count)")
                        .foregroundStyle(.secondary).font(.footnote)
                }
                .padding(20)
                .background(.black.opacity(0.75), in: RoundedRectangle(cornerRadius: 14))

                Spacer()

                VStack(spacing: 16) {
                    Image(systemName: isFavorite ? "heart.fill" : "heart")
                        .font(.title)
                        .foregroundStyle(isFavorite ? .red : .white)
                    Text("▲ Favorit").font(.caption).foregroundStyle(.secondary)
                }
                .padding(20)
                .background(.black.opacity(0.75), in: RoundedRectangle(cornerRadius: 14))
            }
            .padding(.horizontal, 60)
            .padding(.bottom, 50)
        }
    }

    // MARK: Controls

    private func handleMove(_ dir: MoveCommandDirection) {
        switch dir {
        case .left:
            guard !photos.isEmpty else { return }
            currentIndex = (currentIndex - 1 + photos.count) % photos.count
            isFavorite = photos[currentIndex].is_favorite
        case .right:
            guard !photos.isEmpty else { return }
            currentIndex = (currentIndex + 1) % photos.count
            isFavorite = photos[currentIndex].is_favorite
        case .up:
            isFavorite.toggle()
            let id = current.id
            Task { await api.toggleFavorite(photoId: id) }
            showInfoBriefly()
        default:
            break
        }
    }

    private func toggleInfo() {
        showInfo.toggle()
        if showInfo { scheduleHide() }
    }

    private func showInfoBriefly() {
        showInfo = true
        scheduleHide()
    }

    private func scheduleHide() {
        infoHideTask?.cancel()
        infoHideTask = Task {
            try? await Task.sleep(for: .seconds(5))
            if !Task.isCancelled { showInfo = false }
        }
    }

    private func updatePlayer() {
        player?.pause()
        player = nil
        guard current.is_video,
              let url = api.videoStreamURL(photoId: current.id) else { return }
        let p = AVPlayer(url: url)
        p.play()
        player = p
    }
}
