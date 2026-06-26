import SwiftUI
import Photos

/// Automatic camera-roll upload. Scans the photo library for assets taken on/after
/// a configurable date and uploads the ones not yet sent (tracked by localIdentifier),
/// using the existing /v1/upload endpoint — which files them into the user's own
/// Upload/ tree on the server. Originals are sent via PHAssetResourceManager (works
/// for both photos and videos).
@MainActor
final class AutoUploadManager: ObservableObject {
    static let shared = AutoUploadManager()

    @AppStorage("autoUpload.enabled") var enabled = false
    /// Only auto-upload assets taken on/after this date. 0 = no lower bound (all).
    @AppStorage("autoUpload.fromDate") var fromDateTS: Double = 0

    @Published var running = false
    @Published var done = 0
    @Published var total = 0
    @Published var lastResult: String?

    private let uploadedKey = "autoUpload.uploadedIDs"
    private var uploadedIDs: Set<String> {
        get { Set(UserDefaults.standard.stringArray(forKey: uploadedKey) ?? []) }
        set { UserDefaults.standard.set(Array(newValue), forKey: uploadedKey) }
    }

    var fromDate: Date {
        get { fromDateTS > 0 ? Date(timeIntervalSince1970: fromDateTS) : Date(timeIntervalSince1970: 0) }
        set { fromDateTS = newValue.timeIntervalSince1970 }
    }

    /// Entry point — call on app foreground. No-op unless enabled and authorized.
    func runIfEnabled(api: APIClient) async {
        guard enabled, api.loggedIn, !running else { return }
        await run(api: api)
    }

    func run(api: APIClient) async {
        guard !running else { return }
        let status = await requestAuth()
        guard status == .authorized || status == .limited else {
            lastResult = "Kein Fotozugriff erlaubt"; return
        }
        running = true; done = 0; lastResult = nil
        defer { running = false }

        let opts = PHFetchOptions()
        if fromDateTS > 0 {
            opts.predicate = NSPredicate(format: "creationDate >= %@", fromDate as NSDate)
        }
        opts.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: true)]
        let assets = PHAsset.fetchAssets(with: opts)

        var pending: [PHAsset] = []
        let seen = uploadedIDs
        assets.enumerateObjects { a, _, _ in
            if (a.mediaType == .image || a.mediaType == .video) && !seen.contains(a.localIdentifier) {
                pending.append(a)
            }
        }
        total = pending.count
        if pending.isEmpty { lastResult = "Nichts Neues zum Hochladen"; return }

        var ok = 0, dup = 0, fail = 0
        for asset in pending {
            do {
                let (data, name, mime) = try await exportOriginal(asset)
                let r = try await api.uploadFile(data: data, filename: name, mime: mime)
                // Server status is "accepted" | "duplicate" | "error". Only mark a
                // local asset as uploaded when the server actually took it — an
                // "error" (or any unexpected status) must NOT be recorded as done,
                // otherwise the photo is silently dropped from backup forever.
                switch r.status {
                case "accepted": ok += 1; markUploaded(asset.localIdentifier)
                case "duplicate": dup += 1; markUploaded(asset.localIdentifier)
                default: fail += 1   // "error" / unknown → retry next run, don't mark
                }
            } catch {
                fail += 1
            }
            done += 1
        }
        lastResult = "\(ok) hochgeladen, \(dup) Duplikate" + (fail > 0 ? ", \(fail) Fehler" : "")
    }

    private func markUploaded(_ id: String) {
        var s = uploadedIDs; s.insert(id); uploadedIDs = s
    }

    private func requestAuth() async -> PHAuthorizationStatus {
        await withCheckedContinuation { cont in
            PHPhotoLibrary.requestAuthorization(for: .readWrite) { cont.resume(returning: $0) }
        }
    }

    /// Original bytes + filename + mime via the asset's primary resource (photo or video).
    private func exportOriginal(_ asset: PHAsset) async throws -> (Data, String, String) {
        let resources = PHAssetResource.assetResources(for: asset)
        let preferred: [PHAssetResourceType] = asset.mediaType == .video
            ? [.video, .fullSizeVideo]
            : [.photo, .fullSizePhoto]
        guard let res = preferred.compactMap({ t in resources.first { $0.type == t } }).first
                ?? resources.first else {
            throw APIClient.APIError.decode
        }
        let opts = PHAssetResourceRequestOptions()
        opts.isNetworkAccessAllowed = true   // fetch from iCloud if needed
        var buf = Data()
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            PHAssetResourceManager.default().requestData(for: res, options: opts) { chunk in
                buf.append(chunk)
            } completionHandler: { err in
                if let err { cont.resume(throwing: err) } else { cont.resume(returning: ()) }
            }
        }
        let name = res.originalFilename
        let ext = (name as NSString).pathExtension.lowercased()
        let mime: String
        switch ext {
        case "jpg", "jpeg": mime = "image/jpeg"
        case "png": mime = "image/png"
        case "heic": mime = "image/heic"
        case "mov": mime = "video/quicktime"
        case "mp4", "m4v": mime = "video/mp4"
        default: mime = asset.mediaType == .video ? "video/quicktime" : "image/jpeg"
        }
        return (buf, name, mime)
    }
}
