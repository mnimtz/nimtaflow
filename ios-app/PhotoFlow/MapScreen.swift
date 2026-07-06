import SwiftUI
import MapKit
import CoreLocation

// MARK: - Map style preference

enum MapStylePref: String, CaseIterable {
    case standard = "standard"
    case satellit = "satellit"
    case hybrid   = "hybrid"
    case globus   = "globus"

    var label: String {
        switch self {
        case .standard: return "Standard"
        case .satellit: return "Satellit"
        case .hybrid:   return "Hybrid"
        case .globus:   return "Globus (3D)"
        }
    }
    var icon: String {
        switch self {
        case .standard: return "map"
        case .satellit: return "globe.europe.africa.fill"
        case .hybrid:   return "map.fill"
        case .globus:   return "rotate.3d"
        }
    }
    var mapStyle: MapStyle {
        switch self {
        case .standard: return .standard(elevation: .flat)
        case .satellit: return .imagery(elevation: .flat)
        case .hybrid:   return .hybrid(elevation: .flat)
        case .globus:   return .imagery(elevation: .realistic)
        }
    }
    /// Kartenstil hat keine flache Oberfläche → Kamerabereich schwer erzwingbar
    var isGlobe: Bool { self == .globus }
}

// MARK: - Location provider

/// Live device location for the map: requests "when in use" permission and
/// publishes the current position so the map can show a blue "you are here" dot
/// and recenter on demand.
final class LocationProvider: NSObject, ObservableObject, CLLocationManagerDelegate {
    private let mgr = CLLocationManager()
    @Published var coordinate: CLLocationCoordinate2D?
    @Published var authorized = false

    override init() {
        super.init()
        mgr.delegate = self
        mgr.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }
    func request() { mgr.requestWhenInUseAuthorization() }
    func locationManagerDidChangeAuthorization(_ m: CLLocationManager) {
        authorized = m.authorizationStatus == .authorizedWhenInUse || m.authorizationStatus == .authorizedAlways
        if authorized { m.startUpdatingLocation() }
    }
    func locationManager(_ m: CLLocationManager, didUpdateLocations locs: [CLLocation]) {
        if let c = locs.last?.coordinate { coordinate = c }
    }
    func locationManager(_ m: CLLocationManager, didFailWithError error: Error) {}
}

/// Photo map with SERVER-SIDE clustering. Instead of pulling 27k points, it asks
/// the server for grid-clustered bundles of the visible region and refetches
/// (finer grid) as you pan/zoom — so it's tiny and fast at any scale.
struct MapScreen: View {
    @EnvironmentObject var api: APIClient
    @EnvironmentObject var store: Store
    @AppStorage("map_style_pref") private var stylePrefRaw = MapStylePref.globus.rawValue
    @State private var clusters: [MapClusterV1] = []
    @State private var selected: PhotoV1?
    @State private var camera: MapCameraPosition = .region(
        MKCoordinateRegion(center: .init(latitude: 25, longitude: 10),
                           span: MKCoordinateSpan(latitudeDelta: 130, longitudeDelta: 130)))
    @State private var region: MKCoordinateRegion?
    @State private var loading = false
    @State private var mapError: String?
    @State private var clusterPhotos: [PhotoV1] = []
    @State private var showClusterSheet = false
    @StateObject private var loc = LocationProvider()
    @State private var pendingRecenter = false
    @State private var autocentered = false
    private let gridCols = [GridItem(.adaptive(minimum: 100), spacing: 2)]

    private var stylePref: MapStylePref {
        MapStylePref(rawValue: stylePrefRaw) ?? .globus
    }

    private func recenter(on c: CLLocationCoordinate2D) {
        // Beim Recenter aus dem Globus-Modus raus — sonst wirkt der Span nicht.
        if stylePref.isGlobe { stylePrefRaw = MapStylePref.standard.rawValue }
        withAnimation(.easeInOut(duration: 0.6)) {
            camera = .region(MKCoordinateRegion(center: c,
                span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)))
        }
    }

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
                // UserAnnotation() schlägt im Imagery/Globus-Modus zuverlässig fehl —
                // eigene Nadel aus loc.coordinate, sichtbar in allen Map-Stilen.
                if let userCoord = loc.coordinate {
                    Annotation("Mein Standort", coordinate: userCoord) {
                        ZStack {
                            Circle()
                                .fill(Color.blue.opacity(0.25))
                                .frame(width: 28, height: 28)
                            Circle()
                                .fill(Color.blue)
                                .frame(width: 14, height: 14)
                                .overlay(Circle().stroke(.white, lineWidth: 2.5))
                                .shadow(color: .black.opacity(0.3), radius: 3, y: 1)
                        }
                    }
                }
            }
            .mapStyle(stylePref.mapStyle)
            .onMapCameraChange(frequency: .onEnd) { ctx in
                region = ctx.region
                Task { await loadClusters(ctx.region) }
            }
            .navigationTitle("Karte")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Menu {
                        ForEach(MapStylePref.allCases, id: \.rawValue) { s in
                            Button {
                                stylePrefRaw = s.rawValue
                                // Zum Globus wechseln → Kamera auf Weltansicht zoomen
                                if s.isGlobe {
                                    let c = region?.center ?? CLLocationCoordinate2D(latitude: 25, longitude: 10)
                                    withAnimation(.easeInOut(duration: 0.8)) {
                                        camera = .region(MKCoordinateRegion(center: c,
                                            span: MKCoordinateSpan(latitudeDelta: 130, longitudeDelta: 130)))
                                    }
                                }
                            } label: {
                                Label(s.label, systemImage: stylePref == s ? "checkmark" : s.icon)
                            }
                        }
                    } label: {
                        Label(stylePref.label, systemImage: stylePref.icon)
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        loc.request()
                        if let c = loc.coordinate {
                            recenter(on: c)
                        } else {
                            pendingRecenter = true
                        }
                    } label: { Label("Mein Standort", systemImage: "location.fill") }
                }
            }
            .onAppear {
                loc.request()
                // Cluster sofort laden — onMapCameraChange feuert erst nach Nutzerinteraktion,
                // daher initiale Weltansicht manuell anfragen und dann autocenter.
                if !autocentered {
                    let worldRegion = MKCoordinateRegion(
                        center: .init(latitude: 25, longitude: 10),
                        span: MKCoordinateSpan(latitudeDelta: 130, longitudeDelta: 130))
                    Task { await loadClusters(worldRegion) }
                }
            }
            .onReceive(loc.$coordinate.compactMap { $0 }) { c in
                if pendingRecenter { pendingRecenter = false; recenter(on: c) }
            }
            .overlay(alignment: .top) {
                // Assistent-Karten-Filter-Banner (Phase 1)
                if let f = store.chatMapFilter, !f.isEmpty {
                    HStack(spacing: 8) {
                        Image(systemName: "sparkles").foregroundStyle(.indigo)
                        Text("Karte gefiltert: \(f.label)")
                            .font(.footnote.weight(.medium))
                        Spacer()
                        Button { store.chatMapFilter = nil } label: {
                            Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                        }
                    }
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .background(.ultraThinMaterial)
                    .padding(.top, 4)
                }
            }
            .overlay(alignment: .bottom) {
                if loading || mapError != nil {
                    Text(loading ? "lädt…" : (mapError ?? "")).font(.caption).padding(8)
                        .background(.ultraThinMaterial, in: Capsule()).padding(.bottom, 4)
                }
            }
            .onChange(of: store.chatMapFilter) { _, _ in
                // Filter geändert → Cluster neu laden mit neuen Parametern
                if let r = region { Task { await loadClusters(r) } }
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
        let mapFilter = store.chatMapFilter
        do {
            clusters = try await api.mapClusters(minLat: minLat, minLng: minLng,
                                                 maxLat: maxLat, maxLng: maxLng, grid: 12,
                                                 personId: mapFilter?.personId,
                                                 dateFrom: mapFilter?.dateFrom,
                                                 dateTo: mapFilter?.dateTo)
            // Beim ersten Laden auf den Schwerpunkt der echten Fotos zentrieren
            // statt bei einem hardcodierten Globus-Startpunkt zu bleiben.
            if !autocentered, !clusters.isEmpty {
                autocentered = true
                autofitClusters()
            }
        } catch is CancellationError {
        } catch {
            mapError = "Karte: \((error as NSError).localizedDescription)"
        }
        loading = false
    }

    private func autofitClusters() {
        let lats = clusters.map(\.latitude)
        let lngs = clusters.map(\.longitude)
        guard let minLat = lats.min(), let maxLat = lats.max(),
              let minLng = lngs.min(), let maxLng = lngs.max() else { return }
        let centerLat = (minLat + maxLat) / 2
        let centerLng = (minLng + maxLng) / 2
        // Padding-Faktor 1.5, Mindest-Span 8° damit man nicht blind reinzoomt
        let spanLat = max((maxLat - minLat) * 1.5, 8)
        let spanLng = max((maxLng - minLng) * 1.5, 8)
        if stylePref.isGlobe { stylePrefRaw = MapStylePref.standard.rawValue }
        withAnimation(.easeInOut(duration: 1.0)) {
            camera = .region(MKCoordinateRegion(
                center: .init(latitude: centerLat, longitude: centerLng),
                span: MKCoordinateSpan(latitudeDelta: min(spanLat, 100),
                                      longitudeDelta: min(spanLng, 150))))
        }
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
