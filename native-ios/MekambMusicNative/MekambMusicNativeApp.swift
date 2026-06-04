import SwiftUI

@main
struct MekambMusicNativeApp: App {
    @StateObject private var appState: AppState

    init() {
        UserDefaults.standard.register(defaults: [
            "mekambMusicApiEndpoint": "http://13.53.237.20:8000"
        ])
        _appState = StateObject(wrappedValue: AppState())
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appState)
                .preferredColorScheme(.dark)
        }
    }
}
