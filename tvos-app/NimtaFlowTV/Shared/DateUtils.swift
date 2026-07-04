import Foundation

enum DateUtils {
    private static let displayFmt: DateFormatter = {
        let f = DateFormatter(); f.dateStyle = .long; f.timeStyle = .none
        f.locale = Locale(identifier: "de_DE"); return f
    }()
    private static let monthFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "MMMM yyyy"
        f.locale = Locale(identifier: "de_DE"); return f
    }()
    private static let dateOnlyFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; return f
    }()
    private static let isoFull = ISO8601DateFormatter()
    private static let isoNoFrac: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime]; return f
    }()

    static func parse(_ s: String?) -> Date? {
        guard let s else { return nil }
        return isoFull.date(from: s)
            ?? isoNoFrac.date(from: s)
            ?? dateOnlyFmt.date(from: String(s.prefix(10)))
    }

    static func displayDate(_ s: String?) -> String {
        guard let d = parse(s) else { return "Unbekannt" }
        return displayFmt.string(from: d)
    }

    static func monthYear(_ s: String?) -> String {
        guard let d = parse(s) else { return "Unbekannt" }
        return monthFmt.string(from: d)
    }

    // Groups by YYYY-MM prefix
    static func monthKey(_ s: String?) -> String {
        guard let s, s.count >= 7 else { return "0000-00" }
        return String(s.prefix(7))
    }

    // Human-readable duration for videos
    static func duration(_ seconds: Double?) -> String {
        guard let s = seconds, s > 0 else { return "" }
        let total = Int(s)
        let m = total / 60; let sec = total % 60
        return String(format: "%d:%02d", m, sec)
    }
}
