import SwiftUI

struct LoginView: View {
    let serverURL: String
    let api: APIClient
    let onLogin: (String) -> Void
    let onBack: () -> Void

    @State private var deviceResp: DeviceCodeResponse? = nil
    @State private var error: String? = nil
    @State private var polling = false
    @State private var qrImage: UIImage? = nil

    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.05, green: 0.05, blue: 0.15), .black],
                           startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea()

            VStack(spacing: 40) {
                if let err = error {
                    VStack(spacing: 20) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 60))
                            .foregroundStyle(.orange)
                        Text(err)
                            .font(.title3)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                        Button("Zurück", action: onBack)
                            .buttonStyle(.borderedProminent)
                    }
                } else if let resp = deviceResp {
                    HStack(spacing: 80) {
                        VStack(alignment: .leading, spacing: 20) {
                            Text("Mit Smartphone anmelden")
                                .font(.title.bold())
                                .foregroundStyle(.white)
                            Text("1. Öffne NimtaFlow auf deinem Handy")
                                .font(.title3).foregroundStyle(.secondary)
                            Text("2. Gehe zu Einstellungen → Geräte verknüpfen")
                                .font(.title3).foregroundStyle(.secondary)
                            Text("3. Scanne den QR-Code")
                                .font(.title3).foregroundStyle(.secondary)
                            Divider()
                            Text("Code: \(resp.user_code)")
                                .font(.system(size: 32, weight: .bold, design: .monospaced))
                                .foregroundStyle(.indigo)
                            if polling {
                                HStack(spacing: 12) {
                                    ProgressView()
                                    Text("Warte auf Bestätigung…")
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }

                        if let img = qrImage {
                            Image(uiImage: img)
                                .resizable()
                                .interpolation(.none)
                                .frame(width: 260, height: 260)
                                .cornerRadius(16)
                        } else {
                            RoundedRectangle(cornerRadius: 16)
                                .fill(Color.white.opacity(0.08))
                                .frame(width: 260, height: 260)
                                .overlay(ProgressView())
                        }
                    }
                    .padding(60)
                } else {
                    ProgressView("Verbinde mit Server…")
                        .foregroundStyle(.white)
                }

                Button("Zurück", action: onBack)
                    .buttonStyle(.bordered)
                    .font(.callout)
            }
        }
        .task { await startFlow() }
    }

    private func startFlow() async {
        do {
            let resp = try await api.requestDeviceCode()
            deviceResp = resp
            qrImage = generateQR(resp.qr_url)
            await pollLoop(resp.device_code, interval: resp.interval)
        } catch {
            self.error = "Server nicht erreichbar:\n\(error.localizedDescription)"
        }
    }

    private func pollLoop(_ code: String, interval: Int) async {
        polling = true
        for _ in 0..<60 {
            try? await Task.sleep(for: .seconds(interval))
            guard let result = try? await api.pollDeviceToken(deviceCode: code) else { continue }
            if result.status == "authorized", let token = result.access_token {
                onLogin(token)
                return
            }
        }
        error = "Anmeldung abgelaufen. Bitte erneut versuchen."
        polling = false
    }

    private func generateQR(_ string: String) -> UIImage? {
        guard let data = string.data(using: .utf8),
              let filter = CIFilter(name: "CIQRCodeGenerator") else { return nil }
        filter.setValue(data, forKey: "inputMessage")
        filter.setValue("M", forKey: "inputCorrectionLevel")
        guard let output = filter.outputImage else { return nil }
        let scaled = output.transformed(by: CGAffineTransform(scaleX: 10, y: 10))
        let ctx = CIContext()
        guard let cgImg = ctx.createCGImage(scaled, from: scaled.extent) else { return nil }
        return UIImage(cgImage: cgImg)
    }
}
