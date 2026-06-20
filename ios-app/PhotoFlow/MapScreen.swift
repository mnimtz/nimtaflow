import SwiftUI
import MapKit

/// Photo map with SERVER-SIDE clustering. Instead of pulling 27k points, it asks
/// the server for grid-clustered bundles of the visible region and refetches
/// (finer grid) as you pan/zoom — so it's tiny and fast at any scale.
struct MapScreen: View {
    @EnvironmentObject var api: APIClient
    @State private var clusters: [MapClusterV1] = []
    @State private var globe = true   // start on the 3D globe (world view)
    @State private var selected: PhotoV1?
    @State private var camera: MapCameraPosition = .region(
        MKCoordinateRegion(center: .init(latitude: 25, longitude: 10),
                           span: MKCoordinateSpan(latitudeDelta: 130, longitudeDelta: 130)))
    @State private var region: MKCoordinateRegion?
    @State private var loading = false
    @State private var mapError: String?
    @State private var clusterPhotos: [PhotoV1] = []
    @State private var showClusterSheet = false
    private let gridCols = [GridItem(.adaptive(minimum: 100), spacing: 2)]

    var body: some View {
        NavigationStack {
            Map(position: $camera) {
                ForEach(Array(clusters.enumerated()), id: \.offset) { _, c in
                    Annotation("", coordinate: .init(latitude: c.latitude, longitude: c.longitude)) {
                        if c.count == 1 {
                            Circle().fill(c.is_video ? Color.purple : Color.indigo)
                                .frame(width: 15, height: 15)
                                .overlay(Circle().stroke(.white, lineWidth: 2))
                                .onTapGesture { if let id = c.photo_id { Task { selected = try? await api.photo(id) } } }
                        } else {
                            Text("\(c.count)")
                                .font(.caption.bold()).foregroundStyle(.white)
                                .padding(8).frame(minWidth: 36, minHeight: 36)
                                .background(Color.indigo.opacity(0.9), in: Circle())
                                .overlay(Circle().stroke(.white, lineWidth: 2))
                                .onTapGesture {
                                    if c.count <= 30 { Task { await openCluster(c) } }
                                    else { zoomIn(.init(latitude: c.latitude, longitude: c.longitude)) }
                                }
                        }
                    }
                }
            }
            .mapStyle(globe ? .imagery(elevation: .realistic) : .standard(elevation: .flat))
            .onMapCameraChange(frequency: .onEnd) { ctx in
                region = ctx.region
                Task { await loadClusters(ctx.region) }
            }
            .navigationTitle("Karte")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        globe.toggle()
                        if globe {
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
                if loading || mapError != nil {
                    Text(loading ? "lädt…" : (mapError ?? "")).font(.caption).padding(8)
                        .background(.ultraThinMaterial, in: Capsule()).padding(.bottom, 4)
                }
            }
            .fullScreenCover(item: $selected) { p in PhotoPager(photos: [p], start: p) }
            .sheet(isPresented: $showClusterSheet) {
                NavigationStack {
                    ScrollView {
                        LazyVGrid(columns: gridCols, spacing: 2) {
                            ForEach(clusterPhotos) { p in
                                PhotoTile(photo: p).onTapGesture { selected = p; showClusterSheet = false }
                            }
                        }.padding(2)
                    }
                    .navigationTitle("\(clusterPhotos.count) Fotos hier")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Fertig") { showClusterSheet = false } } }
                }
            }
        }
    }

    private func openCluster(_ c: MapClusterV1) async {
        // bbox = one grid cell around the cluster centroid (captures its points)
        let span = region?.span ?? MKCoordinateSpan(latitudeDelta: 1, longitudeDelta: 1)
        let dLat = max(span.latitudeDelta / 11, 0.0005)
        let dLng = max(span.longitudeDelta / 11, 0.0005)
        loading = true
        let photos = (try? await api.mapPhotos(minLat: c.latitude - dLat, minLng: c.longitude - dLng,
                                               maxLat: c.latitude + dLat, maxLng: c.longitude + dLng)) ?? []
        loading = false
        if !photos.isEmpty { clusterPhotos = photos; showClusterSheet = true }
        else { zoomIn(.init(latitude: c.latitude, longitude: c.longitude)) }
    }

    private func loadClusters(_ r: MKCoordinateRegion) async {
        let minLat = r.center.latitude - r.span.latitudeDelta / 2
        let maxLat = r.center.latitude + r.span.latitudeDelta / 2
        let minLng = r.center.longitude - r.span.longitudeDelta / 2
        let maxLng = r.center.longitude + r.span.longitudeDelta / 2
        loading = true; mapError = nil
        do {
            clusters = try await api.mapClusters(minLat: minLat, minLng: minLng,
                                                 maxLat: maxLat, maxLng: maxLng, grid: 12)
        } catch is CancellationError {
        } catch {
            mapError = "Karte: \((error as NSError).localizedDescription)"
        }
        loading = false
    }

    private func zoomIn(_ c: CLLocationCoordinate2D) {
        let span = region?.span ?? MKCoordinateSpan(latitudeDelta: 8, longitudeDelta: 8)
        withAnimation {
            camera = .region(MKCoordinateRegion(center: c, span: MKCoordinateSpan(
                latitudeDelta: max(0.003, span.latitudeDelta / 4),
                longitudeDelta: max(0.003, span.longitudeDelta / 4))))
        }
    }
}
