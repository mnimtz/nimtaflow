import SwiftUI
import MapKit

/// Photo map with zoom-based clustering. Loads ALL geo-tagged photos (tens of
/// thousands) as lightweight points and groups them into a grid per the visible
/// region — so it stays smooth instead of rendering 27k pins at once.
struct MapScreen: View {
    @EnvironmentObject var api: APIClient
    @State private var points: [MapPointV1] = []
    @State private var globe = false
    @State private var selected: PhotoV1?
    @State private var region: MKCoordinateRegion?
    @State private var camera: MapCameraPosition = .automatic
    @State private var loading = false

    struct Cluster: Identifiable {
        let id: Int
        let coordinate: CLLocationCoordinate2D
        let count: Int
        let photoId: Int?
        let isVideo: Bool
    }

    var body: some View {
        NavigationStack {
            Map(position: $camera) {
                ForEach(clusters) { c in
                    Annotation("", coordinate: c.coordinate) {
                        if c.count == 1 {
                            Circle().fill(c.isVideo ? Color.purple : Color.indigo)
                                .frame(width: 15, height: 15)
                                .overlay(Circle().stroke(.white, lineWidth: 2))
                                .onTapGesture { if let id = c.photoId { Task { selected = try? await api.photo(id) } } }
                        } else {
                            Text("\(c.count)")
                                .font(.caption.bold()).foregroundStyle(.white)
                                .padding(8).frame(minWidth: 34, minHeight: 34)
                                .background(Color.indigo.opacity(0.9), in: Circle())
                                .overlay(Circle().stroke(.white, lineWidth: 2))
                                .onTapGesture { zoomIn(c.coordinate) }
                        }
                    }
                }
            }
            .mapStyle(globe ? .imagery(elevation: .realistic) : .standard(elevation: .flat))
            .onMapCameraChange(frequency: .onEnd) { ctx in region = ctx.region }
            .navigationTitle("Karte")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        globe.toggle()
                        if globe {
                            // The 3D globe only shows when zoomed far out → pull the
                            // camera back to a world view so the sphere is visible.
                            let c = region?.center ?? CLLocationCoordinate2D(latitude: 25, longitude: 10)
                            withAnimation(.easeInOut(duration: 0.8)) {
                                camera = .region(MKCoordinateRegion(center: c,
                                    span: MKCoordinateSpan(latitudeDelta: 130, longitudeDelta: 130)))
                            }
                        }
                    } label: {
                        Label(globe ? "Karte" : "Globus", systemImage: globe ? "map" : "globe.europe.africa.fill")
                    }
                }
            }
            .overlay(alignment: .bottom) {
                Text(loading ? "lädt…" : "\(points.count) Fotos mit GPS")
                    .font(.caption).padding(8)
                    .background(.ultraThinMaterial, in: Capsule()).padding(.bottom, 4)
            }
            .task {
                if points.isEmpty {
                    loading = true
                    points = (try? await api.mapPoints()) ?? []
                    loading = false
                }
            }
            .fullScreenCover(item: $selected) { p in PhotoPager(photos: [p], start: p) }
        }
    }

    private func zoomIn(_ c: CLLocationCoordinate2D) {
        let span = region?.span ?? MKCoordinateSpan(latitudeDelta: 8, longitudeDelta: 8)
        withAnimation {
            camera = .region(MKCoordinateRegion(center: c, span: MKCoordinateSpan(
                latitudeDelta: max(0.002, span.latitudeDelta / 4),
                longitudeDelta: max(0.002, span.longitudeDelta / 4))))
        }
    }

    /// Grid-cluster the points that fall inside the current region.
    private var clusters: [Cluster] {
        guard let region else {
            // Before the first camera event: show a light sample so we never try
            // to draw all 27k at once.
            let step = max(1, points.count / 250)
            return stride(from: 0, to: points.count, by: step).enumerated().map { i, idx in
                let p = points[idx]
                return Cluster(id: i, coordinate: .init(latitude: p.latitude, longitude: p.longitude),
                               count: 1, photoId: p.id, isVideo: p.is_video)
            }
        }
        let latMin = region.center.latitude - region.span.latitudeDelta / 2
        let latMax = region.center.latitude + region.span.latitudeDelta / 2
        let lngMin = region.center.longitude - region.span.longitudeDelta / 2
        let lngMax = region.center.longitude + region.span.longitudeDelta / 2
        let visible = points.filter {
            $0.latitude >= latMin && $0.latitude <= latMax && $0.longitude >= lngMin && $0.longitude <= lngMax
        }
        let cols = 11.0
        let cellLat = max(region.span.latitudeDelta / cols, 1e-6)
        let cellLng = max(region.span.longitudeDelta / cols, 1e-6)
        var grid: [Int: [MapPointV1]] = [:]
        for p in visible {
            let key = Int((p.latitude / cellLat).rounded()) * 100_000 + Int((p.longitude / cellLng).rounded())
            grid[key, default: []].append(p)
        }
        return grid.values.enumerated().map { i, group in
            let lat = group.reduce(0.0) { $0 + $1.latitude } / Double(group.count)
            let lng = group.reduce(0.0) { $0 + $1.longitude } / Double(group.count)
            return Cluster(id: i, coordinate: .init(latitude: lat, longitude: lng),
                           count: group.count,
                           photoId: group.count == 1 ? group[0].id : nil,
                           isVideo: group.count == 1 ? group[0].is_video : false)
        }
    }
}
