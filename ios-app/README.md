# PhotoFlow — iOS App (SwiftUI)

A native client for your PhotoFlow server. Talks to the `/api/v1` feed API plus
the `/api` management endpoints (rename/merge people, relationships).

**Features (v1):** Login, photo gallery (grid + full-screen swipe/zoom + favorite),
people (browse, rename, merge), map with 2D ↔ 3D-globe toggle, relationships
(view & add per person), settings (server URL, login). iOS 17+.

## Build & run (on a Mac)

You need **Xcode 15+**. The project is described by `project.yml` (XcodeGen) so it
isn't checked in as a fragile `.xcodeproj`.

```bash
# one-time: accept the Xcode licence + install the project generator
sudo xcodebuild -license accept
brew install xcodegen

cd ios-app
xcodegen generate          # creates PhotoFlow.xcodeproj
open PhotoFlow.xcodeproj
```

In Xcode: select a Simulator (or your iPhone), press **Run** (⌘R).
For a real device, set your Apple **Team** under Signing & Capabilities.

**No XcodeGen?** Create a new iOS App in Xcode named `PhotoFlow`, delete the
generated `ContentView.swift`/`*App.swift`, then drag the `PhotoFlow/` source
folder in. Set the deployment target to iOS 17 and add the Info.plist keys from
`project.yml` (notably `NSAppTransportSecurity → NSAllowsArbitraryLoads = YES`,
since the server is plain HTTP on the LAN).

## Configure
First launch → **Einstellungen** tab → set the server URL (default
`http://your-server:8090`). Login is only required if the server has
"Login erzwingen" enabled.

## Notes / next steps
- Images load via the server's absolute URLs; while server login enforcement is
  **off** they load without a token. When you enable enforcement we'll add an
  auth-aware image loader (AsyncImage can't send the Bearer header).
- Token is stored in `UserDefaults` for v1 — move to Keychain before shipping.
- Planned: upload from the app, face-assignment UI, AI-album browsing, slideshow.
