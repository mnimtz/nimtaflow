import Foundation
import SwiftUI

@MainActor
class AppState: ObservableObject {
    @Published var isLoggedIn: Bool = false

    let api = APIClient()

    private let kServerURL = "tv_serverURL"
    private let kToken = "tv_token"

    init() {
        let url = UserDefaults.standard.string(forKey: kServerURL) ?? ""
        let tok = UserDefaults.standard.string(forKey: kToken) ?? ""
        if !url.isEmpty && !tok.isEmpty {
            api.configure(serverURL: url, token: tok)
            isLoggedIn = true
        }
    }

    func login(serverURL: String, token: String) {
        api.configure(serverURL: serverURL, token: token)
        UserDefaults.standard.set(serverURL, forKey: kServerURL)
        UserDefaults.standard.set(token, forKey: kToken)
        isLoggedIn = true
    }

    func logout() {
        api.configure(serverURL: "", token: "")
        UserDefaults.standard.removeObject(forKey: kServerURL)
        UserDefaults.standard.removeObject(forKey: kToken)
        isLoggedIn = false
    }
}
