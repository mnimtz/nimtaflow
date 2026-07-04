import SwiftUI
import CoreImage.CIFilterBuiltins

struct LoginView: View {
    let serverURL: String
    let api: APIClient
    var onSuccess: (String) -> Void
    var onBack: () -> Void

    @State private var codeResponse: DeviceCodeResponse? = nil
    @State private var qrImage: Image? = nil
    @State private var errorMsg: String? = nil
    @State private var pollingTask: Task<Void, Never>? = nil

    var body: some View {
        Group {
            if let err = errorMsg {
                VStack(spacing: 24) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.system(size: 60)).foregroundStyle(.orange)
                    Text("Verbindungsfehler").font(.title).bold()
                    Text(err).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    Button("Zurück") { onBack() }.buttonStyle(.borderedProminent)
                }
                .padding(60)
            } else if let code = codeResponse {
                loginContent(code: code)
            } else {
                VStack(spacing: 20) {
                    ProgressView()
                    Text("Verbinde mit Server…").foregroundStyle(.secondary)
                }
            }
        }
        .task { await startFlow() }
        .onDisappear { pollingTask?.cancel() }
    }

    private func loginContent(code: DeviceCodeResponse) -> some View {
        HStack(spacing: 80) {
            // QR code
            VStack(spacing: 16) {
                if let qr = qrImage {
                    qr.interpolation(.none)
                        .resizable().frame(width: 260, height: 260)
                        .background(Color.white)
                        .cornerRadius(16)
                } else {
                    RoundedRectangle(cornerRadius: 16)
                        .fill(Color.white)
                        .frame(width: 260, height: 260)
                }
                Text("QR-Code scannen").font(.callout).foregroundStyle(.secondary)
            }

            // Instructions
            VStack(alignment: .leading, spacing: 20) {
                Text("Mit Gerät anmelden").font(.title).bold()

                VStack(alignment: .leading, spacing: 12) {
                    Label("QR-Code mit dem Handy scannen", systemImage: "1.circle.fill")
                    Label("Oder im Browser öffnen:", systemImage: "2.circle.fill")
                    Text(code.qr_url)
                        .font(.system(.body, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .padding(.leading, 32)
                    Label("Code eingeben:", systemImage: "3.circle.fill")
                    Text(code.user_code)
                        .font(.system(.title, design: .monospaced)).bold()
                        .foregroundStyle(.yellow)
                        .padding(.leading, 32)
                    Label("Anmeldung auf Handy bestätigen", systemImage: "4.circle.fill")
                }
                .font(.title3)

                HStack(spacing: 12) {
                    ProgressView()
                    Text("Warte auf Bestätigung…").foregroundStyle(.secondary)
                }
                .padding(.top, 8)

                Button("Zurück") { onBack() }
                    .buttonStyle(.bordered)
                    .padding(.top, 8)
            }
        }
        .padding(80)
    }

    private func startFlow() async {
        api.configure(serverURL: serverURL, token: "")
        do {
            let resp = try await api.requestDeviceCode()
            codeResponse = resp
            qrImage = generateQR(from: resp.qr_url)
            startPolling(deviceCode: resp.device_code, interval: resp.interval)
        } catch {
            errorMsg = error.localizedDescription
        }
    }

    private func startPolling(deviceCode: String, interval: Int) {
        pollingTask = Task {
            let delay = UInt64(max(interval, 3)) * 1_000_000_000
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: delay)
                guard !Task.isCancelled else { return }
                if let poll = try? await api.pollDeviceToken(deviceCode: deviceCode),
                   poll.status == "approved",
                   let tok = poll.access_token {
                    await MainActor.run { onSuccess(tok) }
                    return
                }
            }
        }
    }

    private func generateQR(from string: String) -> Image? {
        let ctx = CIContext()
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        filter.correctionLevel = "M"
        guard let out = filter.outputImage else { return nil }
        let scaled = out.transformed(by: CGAffineTransform(scaleX: 10, y: 10))
        guard let cg = ctx.createCGImage(scaled, from: scaled.extent) else { return nil }
        return Image(decorative: cg, scale: 1)
    }
}
