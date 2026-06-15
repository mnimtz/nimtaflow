import SwiftUI

/// Async image that works with the server's absolute thumbnail URLs.
/// (Auth note: sends no Bearer header — fine while login enforcement is off.)
struct Thumb: View {
    let url: URL?
    var body: some View {
        AsyncImage(url: url) { phase in
            switch phase {
            case .success(let img): img.resizable().scaledToFill()
            case .failure: Color.gray.opacity(0.2).overlay(Image(systemName: "photo").foregroundStyle(.secondary))
            default: Color.gray.opacity(0.15).overlay(ProgressView())
            }
        }
        .clipped()
    }
}

struct Avatar: View {
    let url: URL?
    let initials: String
    var size: CGFloat = 56
    var body: some View {
        ZStack {
            Circle().fill(Color.indigo.opacity(0.25))
            Text(initials).font(.headline).foregroundStyle(.white)
            AsyncImage(url: url) { img in img.resizable().scaledToFill() } placeholder: { Color.clear }
                .clipShape(Circle())
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
    }
}

extension String {
    var firstInitial: String { String(prefix(1)).uppercased() }
}
