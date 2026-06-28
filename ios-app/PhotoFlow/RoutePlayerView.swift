import SwiftUI
import MapKit

/// Animated trip route: walks through the geotagged photos in time order — the
/// travelled line grows, a marker moves, the current photo + date are shown.
/// iOS parity with the web TripsPage route player.
struct RoutePlayerView: View {
    let photos: [PhotoV1]          // geotagged, time-sorted
    @EnvironmentObject var api: APIClient
    @Environment(\.dismiss) var dismiss
    @State private var idx = 0
    @State private var playing = true
    @State private var camera: MapCameraPosition = .automatic

    private var coords: [CLLocationCoordinate2D] {
        photos.compactMap { p in
            guard let lat = p.latitude, let lng = p.longitude else { return nil }
            return CLLocationCoordinate2D(latitude: lat, longitude: lng)
        }
    }
    private let timer = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()

    var body: some View {
        NavigationStack {
            ZStack(alignment: .bottom) {
                Map(position: $camera) {
                    if coords.count > 1 {
                        MapPolyline(coordinates: Array(coords.prefix(idx + 1)))
                            .stroke(.yellow, lineWidth: 4)
                    }
                    if idx < coords.count {
                        Annotation("", coordinate: coords[idx]) {
                            Circle().fill(.yellow).frame(width: 16, height: 16)
                                .overlay(Circle().stroke(.white, lineWidth: 3))
                        }
                    }
                }
                .ignoresSafeArea(edges: .bottom)

                if idx < photos.count {
                    HStack(spacing: 10) {
                        Thumb(url: api.url(photos[idx].thumb_url))
                            .frame(width: 56, height: 56)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(photos[idx].taken_at.map { prettyDate($0) } ?? "")
                                .font(.subheadline).bold()
                            Text("\(idx + 1)/\(coords.count)")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                    .padding(10)
                    .background(.ultraThinMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .padding()
                }
            }
            .navigationTitle("Reiseroute")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { playing.toggle() } label: {
                        Image(systemName: playing ? "pause.fill" : "play.fill")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) { Button("Fertig") { dismiss() } }
            }
            .onAppear { recenter() }
            .onChange(of: idx) { _, _ in recenter() }
            .onReceive(timer) { _ in
                guard playing else { return }
                if idx < coords.count - 1 { idx += 1 } else { playing = false }
            }
        }
    }

    private func recenter() {
        guard idx < coords.count else { return }
        withAnimation {
            camera = .region(MKCoordinateRegion(center: coords[idx],
                span: MKCoordinateSpan(latitudeDelta: 0.5, longitudeDelta: 0.5)))
        }
    }
}
