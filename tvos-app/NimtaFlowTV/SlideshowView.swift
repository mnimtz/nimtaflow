import SwiftUI

struct SlideshowView: View {
    let api: APIClient
    @State private var photos: [PhotoV1] = []
    @State private var current = 0
    @State private var isRunning = false
    @State private var isLoading = true
    @State private var timer: Timer? = nil
    @State private var intervalSec = 5.0

    var body: some View {
        NavigationView {
            ZStack {
                Color.black.ignoresSafeArea()

                if isLoading {
                    ProgressView("Lade Fotos…").foregroundStyle(.white)
                } else if photos.isEmpty {
                    Text("Keine Fotos vorhanden")
                        .font(.title2).foregroundStyle(.secondary)
                } else {
                    // Photo
                    let photo = photos[current]
                    AuthAsyncImage(url: api.fixedURL(photo.original_url), headers: api.authHeaders()) { img in
                        img.resizable().aspectRatio(contentMode: .fit)
                    } placeholder: {
                        AuthAsyncImage(url: api.fixedURL(photo.thumb_medium_url), headers: api.authHeaders()) { img in
                            img.resizable().aspectRatio(contentMode: .fit)
                        } placeholder: {
                            ProgressView()
                        }
                    }
                    .ignoresSafeArea()
                    .animation(.easeInOut(duration: 0.5), value: current)

                    // Controls overlay
                    VStack {
                        Spacer()
                        HStack(spacing: 40) {
                            Button(action: prev) {
                                Image(systemName: "chevron.left.circle.fill")
                                    .font(.system(size: 50)).foregroundStyle(.white.opacity(0.8))
                            }

                            Button(action: togglePlay) {
                                Image(systemName: isRunning ? "pause.circle.fill" : "play.circle.fill")
                                    .font(.system(size: 60)).foregroundStyle(.white)
                            }

                            Button(action: next) {
                                Image(systemName: "chevron.right.circle.fill")
                                    .font(.system(size: 50)).foregroundStyle(.white.opacity(0.8))
                            }
                        }
                        .padding(.bottom, 40)
                        .background(
                            LinearGradient(colors: [.clear, .black.opacity(0.6)],
                                           startPoint: .top, endPoint: .bottom)
                                .ignoresSafeArea()
                        )
                    }

                    // Date overlay top-left
                    VStack(alignment: .leading) {
                        if let date = photo.taken_at {
                            Text(DateUtils.displayDate(date))
                                .font(.callout)
                                .foregroundStyle(.white.opacity(0.7))
                                .padding(20)
                        }
                        Spacer()
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .navigationTitle("Diashow")
            .navigationBarHidden(isRunning)
        }
        .task { await loadPhotos() }
        .onDisappear { stopTimer() }
    }

    private func loadPhotos() async {
        photos = await api.fetchAllPhotos(limit: 300).filter { !$0.is_video }
        photos = photos.shuffled()
        isLoading = false
    }

    private func togglePlay() {
        if isRunning { stopTimer() } else { startTimer() }
    }

    private func startTimer() {
        isRunning = true
        timer = Timer.scheduledTimer(withTimeInterval: intervalSec, repeats: true) { _ in
            Task { @MainActor in next() }
        }
    }

    private func stopTimer() {
        timer?.invalidate()
        timer = nil
        isRunning = false
    }

    private func next() {
        guard !photos.isEmpty else { return }
        current = (current + 1) % photos.count
    }

    private func prev() {
        guard !photos.isEmpty else { return }
        current = current == 0 ? photos.count - 1 : current - 1
    }
}
