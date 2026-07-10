import SwiftUI
import Photos
import Network
import UIKit
#if os(iOS)
import BackgroundTasks
#endif

/// Automatic camera-roll upload. Scans the photo library for assets taken on/after
/// a configurable date and uploads the ones not yet sent (tracked by localIdentifier),
/// using the existing /v1/upload endpoint — which files them into the user's own
/// Upload/ tree on the server. Originals are sent via PHAssetResourceManager (works
/// for both photos and videos).
@MainActor
final class AutoUploadManager: ObservableObject {
    static let shared = AutoUploadManager()

    /// @AppStorage in einer ObservableObject-Klasse feuert kein objectWillChange —
    /// bedingte Views (`if mgr.enabled { … }`, DatePicker etc.) refreshten deshalb
    /// beim Toggle nicht. Fix: @Published-Properties, die UserDefaults als Backing
    /// Store nutzen — Änderungen laufen jetzt korrekt durch SwiftUI's Observation.
    @Published var enabled: Bool = UserDefaults.standard.bool(forKey: "autoUpload.enabled") {
        didSet { UserDefaults.standard.set(enabled, forKey: "autoUpload.enabled") }
    }
    @Published var fromDateTS: Double = UserDefaults.standard.double(forKey: "autoUpload.fromDate") {
        didSet { UserDefaults.standard.set(fromDateTS, forKey: "autoUpload.fromDate") }
    }
    @Published var wifiOnly: Bool = UserDefaults.standard.object(forKey: "autoUpload.wifiOnly") as? Bool ?? true {
        didSet { UserDefaults.standard.set(wifiOnly, forKey: "autoUpload.wifiOnly") }
    }
    @Published var requireCharging: Bool = UserDefaults.standard.bool(forKey: "autoUpload.requireCharging") {
        didSet { UserDefaults.standard.set(requireCharging, forKey: "autoUpload.requireCharging") }
    }
    @Published var background: Bool = UserDefaults.standard.object(forKey: "autoUpload.background") as? Bool ?? true {
        didSet { UserDefaults.standard.set(background, forKey: "autoUpload.background") }
    }
    @Published var nightOnly: Bool = UserDefaults.standard.bool(forKey: "autoUpload.nightOnly") {
        didSet { UserDefaults.standard.set(nightOnly, forKey: "autoUpload.nightOnly") }
    }
    @Published var nightHour: Int = (UserDefaults.standard.object(forKey: "autoUpload.nightHour") as? Int) ?? 2 {
        didSet { UserDefaults.standard.set(nightHour, forKey: "autoUpload.nightHour") }
    }

    nonisolated static let bgTaskID = "com.photoflow.upload"

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
    /// Honors the WLAN/charging conditions (automatic run).
    func runIfEnabled(api: APIClient) async {
        guard enabled, api.loggedIn, !running else { return }
        await run(api: api, enforceConditions: true)
    }

    // ── Conditions (WLAN / charging) ──────────────────────────────────────────
    func conditionsMet() async -> Bool {
        if requireCharging && !Self.isCharging() { return false }
        if wifiOnly {
            let wifi = await Self.onWifi()
            if !wifi { return false }
        }
        return true
    }

    static func isCharging() -> Bool {
#if os(iOS)
        UIDevice.current.isBatteryMonitoringEnabled = true
        let s = UIDevice.current.batteryState
        return s == .charging || s == .full
#else
        return true   // Mac ist immer am Strom
#endif
    }

    /// True only on (non-expensive) Wi-Fi — excludes cellular and personal hotspots.
    static func onWifi() async -> Bool {
        // Box statt captured `var`: @unchecked Sendable ist korrekt, weil die
        // pathUpdateHandler-Queue seriell ist und wir nur einmal schreiben.
        final class Once: @unchecked Sendable { var fired = false }
        let once = Once()
        return await withCheckedContinuation { cont in
            let m = NWPathMonitor()
            m.pathUpdateHandler = { path in
                guard !once.fired else { return }
                once.fired = true
                m.cancel()
                cont.resume(returning: path.status == .satisfied
                    && !path.isExpensive && path.usesInterfaceType(.wifi))
            }
            m.start(queue: DispatchQueue(label: "pf.path.monitor"))
        }
    }

    func run(api: APIClient, enforceConditions: Bool = false) async {
        guard !running else { return }
        if enforceConditions {
            guard await conditionsMet() else {
                lastResult = "Wartet auf Bedingungen (WLAN/Strom)"
                return
            }
        }
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
            if Task.isCancelled { lastResult = "Pausiert (Hintergrund)"; return }
            do {
                let (data, name, mime) = try await exportOriginal(asset)
                let r = try await api.uploadFile(data: data, filename: name, mime: mime)
                switch r.status {
                case "accepted": ok += 1; markUploaded(asset.localIdentifier)
                case "duplicate": dup += 1; markUploaded(asset.localIdentifier)
                default: fail += 1
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

    // ── Background task (BGProcessingTask — iOS only) ─────────────────────────
    /// Register the handler once, at app launch (before launch finishes). No-op on Mac.
    nonisolated static func registerBackgroundTask() {
#if os(iOS)
        BGTaskScheduler.shared.register(forTaskWithIdentifier: bgTaskID, using: nil) { task in
            guard let task = task as? BGProcessingTask else { return }
            scheduleBackground()
            let box = _BGCompletion(task)
            let work = Task { @MainActor in
                await AutoUploadManager.shared.run(api: APIClient.shared, enforceConditions: true)
                box.complete(true)
            }
            task.expirationHandler = { work.cancel(); box.complete(false) }
        }
#endif
    }

    /// Ask iOS to run the upload opportunistically. No-op on Mac.
    nonisolated static func scheduleBackground() {
#if os(iOS)
        let d = UserDefaults.standard
        guard d.bool(forKey: "autoUpload.enabled") else { return }
        guard (d.object(forKey: "autoUpload.background") as? Bool) ?? true else { return }
        let req = BGProcessingTaskRequest(identifier: bgTaskID)
        req.requiresNetworkConnectivity = true
        req.requiresExternalPower = d.bool(forKey: "autoUpload.requireCharging")
        if d.bool(forKey: "autoUpload.nightOnly") {
            let hour = (d.object(forKey: "autoUpload.nightHour") as? Int) ?? 2
            req.earliestBeginDate = nextNight(hour: hour)
        } else {
            req.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        }
        try? BGTaskScheduler.shared.submit(req)
#endif
    }

    nonisolated static func nextNight(hour: Int) -> Date {
        let cal = Calendar.current
        let now = Date()
        var c = cal.dateComponents([.year, .month, .day], from: now)
        c.hour = max(0, min(23, hour)); c.minute = 0
        let today = cal.date(from: c) ?? now
        return today > now ? today : (cal.date(byAdding: .day, value: 1, to: today) ?? today.addingTimeInterval(86400))
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
            throw APIClient.APIError.decode(URLError(.cannotParseResponse))
        }
        let opts = PHAssetResourceRequestOptions()
        opts.isNetworkAccessAllowed = true
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

// MARK: - BGTask completion guard (iOS only)

#if os(iOS)
/// Guards a BGTask so setTaskCompleted is called exactly once (work-done vs. expiry).
final class _BGCompletion: @unchecked Sendable {
    private let lock = NSLock()
    private var done = false
    private let task: BGProcessingTask
    init(_ t: BGProcessingTask) { task = t }
    func complete(_ ok: Bool) {
        lock.lock(); defer { lock.unlock() }
        if done { return }
        done = true
        task.setTaskCompleted(success: ok)
    }
}
#endif
