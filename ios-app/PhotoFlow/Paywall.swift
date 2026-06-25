import SwiftUI

/// Wrap any Pro-only view: shows the content if the user has Pro, otherwise the paywall.
struct ProGate<Content: View>: View {
    @EnvironmentObject var store: Store
    let feature: String
    @ViewBuilder let content: () -> Content
    var body: some View {
        if store.isPro { content() } else { Paywall(feature: feature) }
    }
}

struct Paywall: View {
    @EnvironmentObject var store: Store
    var feature: String = ""

    private let features: [(String, String)] = [
        ("bubble.left.and.text.bubble.right.fill", "KI-Chat über deine Fotos"),
        ("sparkles.tv", "Highlights & KI-Clips"),
        ("magnifyingglass", "Intelligente Suche"),
        ("icloud.and.arrow.up.fill", "Automatischer Upload / Backup"),
    ]

    var body: some View {
        ScrollView {
            VStack(spacing: 22) {
                Image(systemName: "crown.fill")
                    .font(.system(size: 46)).foregroundStyle(.yellow)
                    .padding(.top, 36)
                Text("NimtaFlow Pro").font(.largeTitle.bold())
                if !feature.isEmpty {
                    Text("„\(feature)“ ist eine Pro-Funktion.")
                        .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(features, id: \.1) { f in
                        HStack(spacing: 12) {
                            Image(systemName: f.0).font(.title3).foregroundStyle(.indigo).frame(width: 30)
                            Text(f.1).font(.body)
                            Spacer()
                            Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                        }
                    }
                }
                .padding(18)
                .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 18))
                .padding(.horizontal)

                Text("Einmaliger Kauf — kein Abo. Du verbindest die App mit deinem eigenen Server; deine Daten bleiben bei dir.")
                    .font(.footnote).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center).padding(.horizontal)

                Button {
                    Task { await store.purchase() }
                } label: {
                    HStack {
                        if store.purchasing { ProgressView().tint(.white) }
                        Text(store.purchasing ? "Wird gekauft…" : "Pro freischalten — \(store.priceText)")
                            .font(.headline)
                    }
                    .frame(maxWidth: .infinity).padding()
                    .background(Color.indigo, in: RoundedRectangle(cornerRadius: 14))
                    .foregroundStyle(.white)
                }
                .disabled(store.purchasing || store.proProduct == nil)
                .padding(.horizontal)

                Button("Käufe wiederherstellen") { Task { await store.restore() } }
                    .font(.subheadline).foregroundStyle(.indigo)

                Text("Hast du einen Schlüssel? Unter Mehr → Einstellungen → NimtaFlow Pro einlösen.")
                    .font(.caption).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center).padding(.horizontal).padding(.top, 4)
            }
            .padding(.bottom, 40)
        }
    }
}
