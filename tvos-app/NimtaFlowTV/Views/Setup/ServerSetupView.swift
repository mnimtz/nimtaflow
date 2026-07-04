import SwiftUI

struct ServerSetupView: View {
    var onConnect: (String) -> Void

    @State private var urlText = "http://192.168.0.193:8090"
    @State private var errorMsg: String? = nil

    var body: some View {
        VStack(spacing: 48) {
            VStack(spacing: 16) {
                Image(systemName: "photo.stack")
                    .font(.system(size: 72))
                    .foregroundStyle(.purple)
                Text("NimtaFlow")
                    .font(.largeTitle).bold()
                Text("Serveradresse eingeben um fortzufahren")
                    .font(.title3)
                    .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 12) {
                TextField("http://192.168.0.193:8090", text: $urlText)
                    .textFieldStyle(.plain)
                    .font(.title2)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 14)
                    .background(Color.secondary.opacity(0.15), in: RoundedRectangle(cornerRadius: 12))
                    .frame(width: 720)
                    .autocorrectionDisabled()

                if let msg = errorMsg {
                    Text(msg).foregroundStyle(.red).font(.callout)
                        .padding(.leading, 4)
                }
            }

            Button("Verbinden") { connect() }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        }
    }

    private func connect() {
        let url = urlText.trimmingCharacters(in: .whitespaces)
        guard url.lowercased().hasPrefix("http") else {
            errorMsg = "Bitte vollständige URL eingeben (http://…)"; return
        }
        errorMsg = nil
        onConnect(url)
    }
}
