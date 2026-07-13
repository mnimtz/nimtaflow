// v1.561: "360° & Drohne" - neuer iOS-Tab, identisch zum Web-Layout.
// Filter-Chips (Alle / 360° / Drohne), Grid mit Overlay-Badges, Tap:
// - 360°-Foto -> SceneKit-Kugel mit invertierten Normalen (Gyro-fähig)
// - 360°-Video -> AVPlayer als Kugel-Textur
// - Drohnen-Foto/Video -> Standard-Anzeige + Höhen/Gimbal-Overlay
import SwiftUI
import SceneKit
import AVKit
import CoreMotion
import Combine

struct SpecialView: View {
    @EnvironmentObject var api: APIClient
    @State private var filter: String = "all"   // "all" | "360" | "drone"
    @State private var page: SpecialPage?
    @State private var loading = false
    @State private var err: String?
    @State private var opened: PhotoV1?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Panorama-Aufnahmen und Luftaufnahmen — mit passendem Viewer.")
                        .font(.footnote).foregroundStyle(.secondary)
                        .padding(.horizontal)
                    filterChips
                    if let e = err { Text(e).font(.caption).foregroundStyle(.red).padding(.horizontal) }
                    grid
                }
                .padding(.vertical, 8)
            }
            .navigationTitle("360° & Drohne")
            .task { await load() }
            .refreshable { await load() }
        }
        .fullScreenCover(item: $opened) { p in
            SpecialViewerScreen(photo: p) { opened = nil }
        }
    }

    // MARK: - Chips
    private var filterChips: some View {
        HStack(spacing: 8) {
            chip("Alle", key: "all",
                 badge: (page?.counts?.total_360 ?? 0) + (page?.counts?.total_drone ?? 0))
            chip("360°", key: "360",
                 icon: "globe.europe.africa.fill",
                 badge: page?.counts?.total_360)
            chip("Drohne", key: "drone",
                 icon: "airplane.circle.fill",
                 badge: page?.counts?.total_drone)
            Spacer()
        }
        .padding(.horizontal)
    }

    private func chip(_ label: String, key: String, icon: String? = nil, badge: Int? = nil) -> some View {
        let active = filter == key
        return Button {
            filter = key
            Task { await load() }
        } label: {
            HStack(spacing: 6) {
                if let icon { Image(systemName: icon) }
                Text(label).font(.subheadline)
                if let b = badge, b > 0 {
                    Text("\(b)").font(.caption2).monospacedDigit()
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(active ? .white.opacity(0.25) : Color.gray.opacity(0.2), in: Capsule())
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 8)
            .background(active ? Color.indigo : Color(.secondarySystemGroupedBackground),
                        in: Capsule())
            .foregroundStyle(active ? .white : .primary)
        }
    }

    // MARK: - Grid
    private var grid: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 100), spacing: 4)], spacing: 4) {
            ForEach(page?.items ?? [], id: \.id) { p in
                Button { opened = p } label: {
                    tile(p)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 4)
        .overlay {
            if page != nil && (page!.items.isEmpty) {
                Text("Keine Aufnahmen gefunden.\nDer Erkennungs-Task läuft evtl. noch — in ein paar Minuten erneut prüfen.")
                    .multilineTextAlignment(.center).font(.footnote)
                    .foregroundStyle(.secondary).padding(40)
            }
        }
    }

    private func tile(_ p: PhotoV1) -> some View {
        // v1.563: bei 360°-Fotos Little-Planet-Thumbnail anzeigen.
        let thumbURL: URL? = (p.is_360 == true && !p.is_video)
            ? api.url("/api/v1/photos/\(p.id)/planet")
            : api.url(p.thumb_medium_url)
        return ZStack(alignment: .topLeading) {
            AsyncImage(url: thumbURL) { img in
                img.resizable().aspectRatio(1, contentMode: .fill)
            } placeholder: { Color.gray.opacity(0.2) }
            .aspectRatio(1, contentMode: .fill)
            .frame(maxWidth: .infinity).clipped()
            .clipShape(RoundedRectangle(cornerRadius: 12))

            if p.is_360 == true {
                Label("360°", systemImage: "globe.europe.africa.fill")
                    .labelStyle(.titleAndIcon).font(.caption2).bold()
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(.black.opacity(0.65), in: Capsule())
                    .foregroundStyle(.white).padding(6)
            }
            if p.is_drone == true {
                HStack(spacing: 3) {
                    Image(systemName: "airplane")
                    if let a = p.drone_metadata?.relative_altitude_m {
                        Text("\(Int(a))m")
                    } else {
                        Text("Drohne")
                    }
                }
                .font(.caption2).bold()
                .padding(.horizontal, 6).padding(.vertical, 3)
                .background(.black.opacity(0.65), in: Capsule())
                .foregroundStyle(.white).padding(6)
            }
        }
    }

    private func load() async {
        loading = true; defer { loading = false }
        do {
            page = try await api.specialPhotos(filter: filter, limit: 120)
            err = nil
        } catch {
            err = "Konnte 360°/Drohnen-Liste nicht laden: \(error.localizedDescription)"
        }
    }
}


// MARK: - Fullscreen Viewer
struct SpecialViewerScreen: View {
    @EnvironmentObject var api: APIClient
    let photo: PhotoV1
    let onClose: () -> Void
    // v1.563: bei 360°-Fotos zwei Modi: Sphere-Viewer ODER 4 Perspektiv-Ausschnitte
    @State private var mode: String = "sphere"   // "sphere" | "reframe"

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Color.black.ignoresSafeArea()

            if photo.is_360 == true, !photo.is_video,
               let u = api.url(photo.original_url) {
                if mode == "sphere" {
                    Sphere360PhotoView(imageURL: u).ignoresSafeArea()
                } else {
                    ReframeChooserView(photoId: photo.id)
                }
                VStack {
                    HStack(spacing: 8) {
                        Button { mode = "sphere" } label: {
                            Label("360°", systemImage: "globe.europe.africa.fill")
                                .padding(.horizontal, 10).padding(.vertical, 6)
                                .background(mode == "sphere" ? .white : .black.opacity(0.5),
                                            in: Capsule())
                                .foregroundStyle(mode == "sphere" ? .black : .white)
                        }
                        Button { mode = "reframe" } label: {
                            Label("Perspektiven", systemImage: "camera.viewfinder")
                                .padding(.horizontal, 10).padding(.vertical, 6)
                                .background(mode == "reframe" ? .white : .black.opacity(0.5),
                                            in: Capsule())
                                .foregroundStyle(mode == "reframe" ? .black : .white)
                        }
                        Spacer()
                    }
                    .font(.caption).padding(.horizontal).padding(.top, 8)
                    Spacer()
                }
            } else if photo.is_360 == true, photo.is_video,
                      let u = api.url(photo.video_url ?? "") {
                Sphere360VideoView(videoURL: u)
                    .ignoresSafeArea()
            } else if photo.is_video, let u = api.url(photo.video_url ?? "") {
                VideoPlayer(player: AVPlayer(url: u))
                    .ignoresSafeArea()
            } else if let u = api.url(photo.original_url) {
                AsyncImage(url: u) { img in
                    img.resizable().scaledToFit()
                } placeholder: { ProgressView().tint(.white) }
            }

            if photo.is_drone == true, let m = photo.drone_metadata {
                VStack {
                    Spacer()
                    droneOverlay(m).padding()
                }
            }

            Button { onClose() } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title2).foregroundStyle(.white.opacity(0.9))
            }.padding()
        }
    }

    private func droneOverlay(_ m: PhotoV1.DroneMeta) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Drohnen-Aufnahme", systemImage: "airplane")
                .font(.subheadline).bold()
            if let s = m.story {
                Text(s).font(.callout)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.bottom, 2)
            }
            HStack(spacing: 16) {
                if let r = m.relative_altitude_m {
                    stat("Höhe (rel.)", "\(Int(r)) m")
                }
                if let a = m.absolute_altitude_m {
                    stat("Höhe (GPS)", "\(Int(a)) m")
                }
                if let g = m.gimbal_pitch {
                    stat("Gimbal", "\(Int(g))°")
                }
            }
            if m.make != nil || m.model != nil {
                Text([m.make, m.model].compactMap { $0 }.joined(separator: " "))
                    .font(.caption).foregroundStyle(.white.opacity(0.7))
            }
        }
        .padding(14)
        .background(.black.opacity(0.7), in: RoundedRectangle(cornerRadius: 14))
        .foregroundStyle(.white)
    }
    private func stat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption2).foregroundStyle(.white.opacity(0.6))
            Text(value).font(.body).bold()
        }
    }
}


// MARK: - Reframe-Chooser (4 Perspektiven aus einem 360°)
struct ReframeChooserView: View {
    @EnvironmentObject var api: APIClient
    let photoId: Int
    @State private var selected: Int? = nil
    private let views: [(idx: Int, label: String)] = [
        (0, "Vorne"), (1, "Rechts"), (2, "Hinten"), (3, "Links"),
    ]
    var body: some View {
        Group {
            if let s = selected {
                VStack {
                    Spacer()
                    AsyncImage(url: api.url("/api/v1/photos/\(photoId)/reframe/\(s)")) { img in
                        img.resizable().scaledToFit()
                    } placeholder: { ProgressView().tint(.white) }
                    Spacer()
                    Button { selected = nil } label: {
                        Label("Zurück zu den Perspektiven", systemImage: "arrow.left")
                            .padding(.horizontal, 14).padding(.vertical, 8)
                            .background(.white, in: Capsule())
                            .foregroundStyle(.black)
                    }.padding(.bottom, 30)
                }
            } else {
                ScrollView {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        ForEach(views, id: \.idx) { v in
                            Button { selected = v.idx } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    AsyncImage(url: api.url("/api/v1/photos/\(photoId)/reframe/\(v.idx)")) { img in
                                        img.resizable().aspectRatio(16/9, contentMode: .fill)
                                    } placeholder: { Color.gray.opacity(0.3).aspectRatio(16/9, contentMode: .fill) }
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                                    Text(v.label).font(.subheadline).bold()
                                        .foregroundStyle(.white)
                                }
                            }
                        }
                    }
                    .padding()
                    .padding(.top, 60)
                }
            }
        }
    }
}


// MARK: - 360° Photo (SceneKit-Kugel, invertierte Normalen)
struct Sphere360PhotoView: UIViewRepresentable {
    let imageURL: URL

    func makeUIView(context: Context) -> SCNView {
        let scn = SCNView()
        scn.backgroundColor = .black
        scn.allowsCameraControl = true
        scn.autoenablesDefaultLighting = false
        scn.antialiasingMode = .multisampling4X

        let scene = SCNScene()
        scn.scene = scene

        let cam = SCNCamera()
        cam.fieldOfView = 75
        cam.zNear = 0.01; cam.zFar = 1000
        let camNode = SCNNode(); camNode.camera = cam
        camNode.position = SCNVector3(0, 0, 0.01)
        scene.rootNode.addChildNode(camNode)

        // Kugel mit Radius 50, viel Segmentierung für saubere Textur
        let sphere = SCNSphere(radius: 50)
        sphere.segmentCount = 96
        sphere.isGeodesic = false

        let mat = SCNMaterial()
        mat.diffuse.contents = UIColor.darkGray
        mat.diffuse.mipFilter = .linear
        mat.isDoubleSided = false
        mat.cullMode = .front       // Textur wird von innen sichtbar (invertierte Normale)
        sphere.firstMaterial = mat

        let node = SCNNode(geometry: sphere)
        // X-Spiegelung damit Bild nicht seitenverkehrt ist
        node.scale = SCNVector3(-1, 1, 1)
        scene.rootNode.addChildNode(node)

        // Bild asynchron laden
        Task {
            if let (data, _) = try? await URLSession.shared.data(from: imageURL),
               let img = UIImage(data: data) {
                await MainActor.run {
                    mat.diffuse.contents = img
                }
            }
        }
        return scn
    }
    func updateUIView(_ uiView: SCNView, context: Context) {}
}


// MARK: - 360° Video (AVPlayer als SCNMaterial-Content)
struct Sphere360VideoView: UIViewRepresentable {
    let videoURL: URL

    func makeUIView(context: Context) -> SCNView {
        let scn = SCNView()
        scn.backgroundColor = .black
        scn.allowsCameraControl = true
        scn.antialiasingMode = .multisampling4X

        let scene = SCNScene()
        scn.scene = scene

        let cam = SCNCamera()
        cam.fieldOfView = 75
        let camNode = SCNNode(); camNode.camera = cam
        camNode.position = SCNVector3(0, 0, 0.01)
        scene.rootNode.addChildNode(camNode)

        let sphere = SCNSphere(radius: 50)
        sphere.segmentCount = 96

        let player = AVPlayer(url: videoURL)
        let mat = SCNMaterial()
        mat.diffuse.contents = player
        mat.isDoubleSided = false
        mat.cullMode = .front
        sphere.firstMaterial = mat

        let node = SCNNode(geometry: sphere)
        node.scale = SCNVector3(-1, 1, 1)
        scene.rootNode.addChildNode(node)

        // Loop
        NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime,
            object: player.currentItem, queue: .main
        ) { _ in
            player.seek(to: .zero); player.play()
        }
        player.play()
        return scn
    }
    func updateUIView(_ uiView: SCNView, context: Context) {}
}
