import SwiftUI
import AVKit

struct MediaPlayerView: View {
    let photo: PhotoV1
    let api: APIClient
    let onClose: () -> Void

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if photo.is_video, let videoURL = api.videoStreamURL(photoId: photo.id) {
                VideoPlayer(player: AVPlayer(url: videoURL))
                    .ignoresSafeArea()
            } else if let url = api.fixedURL(photo.original_url) {
                AuthAsyncImage(url: url, headers: api.authHeaders()) { image in
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .ignoresSafeArea()
                } placeholder: {
                    ProgressView()
                }
            }

            VStack {
                HStack {
                    Spacer()
                    Button(action: onClose) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 40))
                            .foregroundStyle(.white.opacity(0.8))
                            .padding(24)
                    }
                }
                Spacer()
                if let date = photo.taken_at {
                    Text(DateUtils.displayDate(date))
                        .font(.callout)
                        .foregroundStyle(.white.opacity(0.7))
                        .padding(.bottom, 24)
                }
            }
        }
        .onExitCommand(perform: onClose)
    }
}
