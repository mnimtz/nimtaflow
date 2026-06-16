import SwiftUI

/// Shown when not logged in (the server enforces login). Server URL + credentials.
struct LoginView: View {
    @EnvironmentObject var api: APIClient
    @State private var server = ""
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        ZStack {
            LinearGradient(colors: [.indigo.opacity(0.35), .black], startPoint: .top, endPoint: .bottom).ignoresSafeArea()
            VStack(spacing: 18) {
                Spacer()
                Image(systemName: "camera.aperture").font(.system(size: 54)).foregroundStyle(.white)
                Text("PhotoFlow").font(.largeTitle.bold()).foregroundStyle(.white)
                Text("Deine private Fotoverwaltung").font(.subheadline).foregroundStyle(.white.opacity(0.7))

                VStack(spacing: 12) {
                    field("Server (http://host:8090)", text: $server, keyboard: .URL)
                    field("E-Mail", text: $email, keyboard: .emailAddress)
                    SecureField("Passwort", text: $password)
                        .textContentType(.password)
                        .padding(12).background(.white.opacity(0.12), in: RoundedRectangle(cornerRadius: 12)).foregroundStyle(.white)

                    Button {
                        Task { await login() }
                    } label: {
                        HStack { if busy { ProgressView().tint(.white) }; Text("Anmelden").bold() }
                            .frame(maxWidth: .infinity).padding(.vertical, 13)
                            .background(.indigo, in: RoundedRectangle(cornerRadius: 12)).foregroundStyle(.white)
                    }.disabled(busy || email.isEmpty || password.isEmpty)
                }
                .padding().background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 18))
                .padding(.horizontal, 24)

                if let error { Text(error).font(.caption).foregroundStyle(.red) }
                Spacer(); Spacer()
            }
        }
        .onAppear { server = api.serverURL }
        .tint(.white)
    }

    @ViewBuilder private func field(_ ph: String, text: Binding<String>, keyboard: UIKeyboardType) -> some View {
        TextField(ph, text: text)
            .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(keyboard)
            .padding(12).background(.white.opacity(0.12), in: RoundedRectangle(cornerRadius: 12)).foregroundStyle(.white)
    }

    func login() async {
        busy = true; defer { busy = false }; error = nil
        api.serverURL = server.trimmingCharacters(in: .whitespaces)
        do { try await api.login(username: email, password: password); password = "" }
        catch { error = "Anmeldung fehlgeschlagen — Server/Zugangsdaten prüfen." }
    }
}
