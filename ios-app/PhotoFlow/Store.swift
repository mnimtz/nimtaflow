import SwiftUI
import StoreKit

/// NimtaFlow Pro — StoreKit 2 entitlement.
///
/// Self-hosted ⇒ the only real paid gate is the on-device App-Store purchase
/// (per Apple ID). `isPro` is true when ANY of these hold:
///   • the user bought Pro (StoreKit entitlement), OR
///   • their connected server marks the account Pro (family / self-host, via key), OR
///   • the launch promo window is still open (everyone free until `promoEnd`).
@MainActor
final class Store: ObservableObject {
    static let proProductID = "email.nimtz.photoflow.pro"

    /// Launch-Promo: bis zu diesem Datum sind alle Pro-Funktionen gratis (Werbung).
    static let promoEnd: Date = Calendar.current.date(from: DateComponents(year: 2026, month: 9, day: 30)) ?? .distantPast

    @Published var proProduct: Product?
    @Published var purchasedPro = false      // StoreKit
    @Published var serverPro = false         // /auth/me.is_pro (eigener Server)
    @Published var purchasing = false
    @Published var ready = false             // erster Entitlement-Check abgeschlossen
    // Chat-Assistent → Galerie-Filter: wenn der Nutzer "Alle N in Galerie öffnen" tippt,
    // landen die Treffer hier; GalleryView beobachtet das und schaltet in den Filtermodus.
    @Published var chatGalleryFilter: [Int]? = nil

    var promoActive: Bool { Date() < Store.promoEnd }
    var isPro: Bool { purchasedPro || serverPro || promoActive }
    var priceText: String { proProduct?.displayPrice ?? "4,99 €" }

    init() {
        // Transaction-Listener läuft die ganze App-Laufzeit (Store ist ein @StateObject)
        // → kein deinit-Cancel nötig (das vermied einen MainActor-Zugriff aus nonisolated deinit).
        _ = listenForTransactions()
        Task { await loadProduct(); await refreshEntitlements(); ready = true }
    }

    func loadProduct() async {
        proProduct = try? await Product.products(for: [Store.proProductID]).first
    }

    func refreshEntitlements() async {
        var owned = false
        for await result in Transaction.currentEntitlements {
            if case .verified(let t) = result, t.productID == Store.proProductID, t.revocationDate == nil {
                owned = true
            }
        }
        purchasedPro = owned
    }

    func purchase() async {
        guard let p = proProduct else { return }
        purchasing = true; defer { purchasing = false }
        guard let result = try? await p.purchase() else { return }
        if case .success(let verification) = result, case .verified(let t) = verification {
            await t.finish()
            // Re-derive from the actual entitlement set (single source of truth) so a
            // pending / Ask-to-Buy / deferred result doesn't leave the UI out of sync.
            await refreshEntitlements()
        }
    }

    func restore() async {
        try? await AppStore.sync()
        await refreshEntitlements()
    }

    /// Server-Entitlement aus /auth/me ziehen (Familie/Self-Host bekommt Pro gratis).
    func syncServer(_ api: APIClient) async {
        struct Me: Decodable { let is_pro: Bool? }
        if let me = try? await api.get("api/auth/me", as: Me.self) { serverPro = me.is_pro ?? false }
    }

    private func listenForTransactions() -> Task<Void, Never> {
        Task.detached { [weak self] in
            for await result in Transaction.updates {
                if case .verified(let t) = result {
                    await t.finish()
                    await self?.refreshEntitlements()
                }
            }
        }
    }
}
