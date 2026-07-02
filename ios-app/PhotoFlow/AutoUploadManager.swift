import SwiftUI
import Photos
import Network
import UIKit
import BackgroundTasks

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
    /// Conditions for AUTOMATIC runs (the manual "Jetzt hochladen" button ignores them).
    @AppStorage("autoUpload.wifiOnly") var wifiOnly = true
    @AppStorage("autoUpload.requireCharging") var requireCharging = false
    /// Run opportunistically in the background (BGProcessingTask). iOS decides the
    /// exact time — typically at night while charging on Wi-Fi, which matches the
    /// conditions below.
    @AppStorage("autoUpload.background") var background = true
    /// Prefer a nightly window: schedule the background task for ~this hour.
    @AppStorage("autoUpload.nightOnly") var nightOnly = false
    @AppStorage("autoUpload.nightHour") var nightHour = 2

    nonisolated(unsafe) static let bgTaskID = "com.photoflow.upload"

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
        UIDevice.current.isBatteryMonitoringEnabled = true
        let s = UIDevice.current.batteryState
        return s == .charging || s == .full
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
            // Stop cleanly if the background task's time runs out (or conditions drop).
            if Task.isCancelled { lastResult = "Pausiert (Hintergrund)"; return }
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

    // ── Background task (BGProcessingTask) ────────────────────────────────────
    /// Register the handler once, at app launch (before launch finishes).
    nonisolated static func registerBackgroundTask() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: bgTaskID, using: nil) { task in
            guard let task = task as? BGProcessingTask else { return }
            scheduleBackground()                         // queue the next opportunistic run
            let box = _BGCompletion(task)
            let work = Task { @MainActor in
                await AutoUploadManager.shared.run(api: APIClient.shared, enforceConditions: true)
                box.complete(true)
            }
            task.expirationHandler = { work.cancel(); box.complete(false) }
        }
    }

    /// Ask iOS to run the upload opportunistically. With nightOnly it targets ~the
    /// chosen hour; otherwise as soon as the conditions (network/power) are met.
    nonisolated static func scheduleBackground() {
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
