import SwiftUI
import UIKit

/// Loads an image from a URL with Bearer auth header.
struct AuthAsyncImage<Content: View, Placeholder: View>: View {
    let url: URL?
    let headers: [String: String]
    @ViewBuilder var content: (Image) -> Content
    @ViewBuilder var placeholder: () -> Placeholder

    @State private var uiImage: UIImage? = nil

    init(
        url: URL?,
        headers: [String: String] = [:],
        @ViewBuilder content: @escaping (Image) -> Content,
        @ViewBuilder placeholder: @escaping () -> Placeholder
    ) {
        self.url = url
        self.headers = headers
        self.content = content
        self.placeholder = placeholder
    }

    var body: some View {
        Group {
            if let img = uiImage {
                content(Image(uiImage: img))
            } else {
                placeholder()
            }
        }
        .task(id: url) {
            guard let url else { return }
            var req = URLRequest(url: url)
            req.timeoutInterval = 20
            for (k, v) in headers { req.setValue(v, forHTTPHeaderField: k) }
            if let (data, _) = try? await URLSession.shared.data(for: req),
               let img = UIImage(data: data) {
                uiImage = img
            }
        }
    }
}
