import SwiftUI

struct ServerSetupView: View {
    let onContinue: (String) -> Void
    @State private var url = "http://"
    @State private var focused = false

    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.05, green: 0.05, blue: 0.15), .black],
                           startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea()

            VStack(spacing: 48) {
                VStack(spacing: 16) {
                    Image(systemName: "photo.stack")
                        .font(.system(size: 80))
                        .foregroundStyle(.indigo)
                    Text("NimtaFlow")
                        .font(.largeTitle.bold())
                        .foregroundStyle(.white)
                    Text("Gib die URL deines NimtaFlow-Servers ein")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }

                VStack(spacing: 24) {
                    TextField("http://192.168.0.193:8090", text: $url)
                        .textFieldStyle(.plain)
                        .font(.title2)
                        .padding()
                        .background(Color.white.opacity(0.08))
                        .cornerRadius(12)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        .frame(maxWidth: 800)

                    Button("Weiter") {
                        let cleaned = url.trimmingCharacters(in: .whitespacesAndNewlines)
                            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                        if !cleaned.isEmpty { onContinue(cleaned) }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.indigo)
                    .font(.headline)
                    .disabled(url.isEmpty || url == "http://")
                }
                .frame(maxWidth: 800)
            }
            .padding(60)
        }
    }
}
