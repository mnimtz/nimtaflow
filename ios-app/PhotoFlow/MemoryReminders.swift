import SwiftUI
import UserNotifications

/// Daily "memories" reminder via LOCAL notifications (no server / no APNs needed).
/// When enabled, schedules a repeating notification at the chosen time that nudges
/// the user to look at today's "X years ago" memories. Tapping opens the app.
@MainActor
final class MemoryReminders: ObservableObject {
    static let shared = MemoryReminders()
    static let notifID = "memories.daily"

    @AppStorage("reminders.enabled") var enabled = false
    @AppStorage("reminders.hour") var hour = 10
    @AppStorage("reminders.minute") var minute = 0

    /// Re-apply the current settings on launch (schedule or clear).
    func sync() {
        if enabled { Task { await schedule() } } else { cancel() }
    }

    func setEnabled(_ on: Bool) {
        enabled = on
        if on { Task { await schedule() } } else { cancel() }
    }

    func reschedule() { if enabled { Task { await schedule() } } }

    private func requestAuth() async -> Bool {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        if settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional {
            return true
        }
        return (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
    }

    private func schedule() async {
        guard await requestAuth() else { enabled = false; return }
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: [Self.notifID])

        let content = UNMutableNotificationContent()
        content.title = "NimtaFlow"
        content.body = "Schau dir deine Erinnerungen von heute an ✨"
        content.sound = .default

        var comps = DateComponents()
        comps.hour = max(0, min(23, hour))
        comps.minute = max(0, min(59, minute))
        let trigger = UNCalendarNotificationTrigger(dateMatching: comps, repeats: true)
        let req = UNNotificationRequest(identifier: Self.notifID, content: content, trigger: trigger)
        try? await center.add(req)
    }

    private func cancel() {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [Self.notifID])
    }
}
