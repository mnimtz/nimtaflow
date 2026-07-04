import SwiftUI

struct PhotoCard: View {
    let photo: PhotoV1
    let api: APIClient

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            AuthAsyncImage(
                url: api.fixedURL(photo.thumb_medium_url),
                headers: api.authHeaders()
            ) { image in
                image.resizable().aspectRatio(contentMode: .fill)
            } placeholder: {
                Rectangle()
                    .fill(Color.secondary.opacity(0.2))
                    .overlay(
                        Image(systemName: photo.is_video ? "video" : "photo")
                            .font(.largeTitle)
                            .foregroundStyle(.secondary)
                    )
            }
            .frame(width: 300, height: 200)
            .clipped()

            if photo.is_video {
                HStack(spacing: 4) {
                    Image(systemName: "play.fill").font(.caption)
                    if let dur = photo.duration_seconds {
                        Text(DateUtils.duration(dur)).font(.caption2)
                    }
                }
                .foregroundStyle(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(.black.opacity(0.65))
                .padding(8)
            }
        }
        .overlay(alignment: .topTrailing) {
            if photo.is_favorite {
                Image(systemName: "heart.fill")
                    .foregroundStyle(.red)
                    .padding(8)
                    .shadow(radius: 2)
            }
        }
        .cornerRadius(12)
    }
}
