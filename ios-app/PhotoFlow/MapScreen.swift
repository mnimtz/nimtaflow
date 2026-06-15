import SwiftUI
import MapKit

struct MapScreen: View {
    @EnvironmentObject var api: APIClient
    @State private var photos: [PhotoV1] = []
    @State private var globe = false
    @State private var selected: PhotoV1?

    var withGps: [PhotoV1] { photos.filter { $0.latitude != nil && $0.longitude != nil } }

    var body: some View {
        NavigationStack {
            Map {
                ForEach(withGps) { p in
                    Annotation(p.filename, coordinate: .init(latitude: p.latitude!, longitude: p.longitude!)) {
                        Thumb(url: api.url(p.thumb_url))
                            .frame(width: 44, height: 44).clipShape(RoundedRectangle(cornerRadius: 8))
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(.white, lineWidth: 2))
                            .onTapGesture { selected = p }
                    }
                }
            }
            // 3D globe / satellite imagery; flat standard otherwise
            .mapStyle(globe ? .imagery(elevation: .realistic) : .standard(elevation: .flat))
            .navigationTitle("Karte")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { globe.toggle() } label: { Label(globe ? "Karte" : "Globus", systemImage: globe ? "map" : "globe.europe.africa.fill") }
                }
            }
            .overlay(alignment: .bottom) {
                Text("\(withGps.count) Fotos mit GPS").font(.caption).padding(8)
                    .background(.ultraThinMaterial, in: Capsule()).padding(.bottom, 4)
            }
            .task { if photos.isEmpty { photos = (try? await api.mapPhotos())?.items ?? [] } }
            .fullScreenCover(item: $selected) { p in PhotoPager(photos: withGps, start: p) }
        }
    }
}
