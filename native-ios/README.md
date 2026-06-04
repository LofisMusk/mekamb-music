# Mekamb Music Native iOS

Native SwiftUI iPhone client for Mekamb Music. This app does not use Electron,
Capacitor, React, Vite, or a WebView. It talks directly to the FastAPI backend
with `URLSession` and streams tracks with `AVPlayer`.

## Open in Xcode

Open this file, not the repository root:

```bash
open native-ios/MekambMusicNative.xcodeproj
```

Then choose the `MekambMusicNative` scheme and an iPhone simulator or your
connected iPhone.

## Connect to the backend

Start the backend first:

```bash
docker compose up --build
```

In the iOS app, open Settings and enter:

- API endpoint: `http://YOUR_MAC_OR_SERVER_LAN_IP:8000`
- API token: the same value as `API_TOKEN` from your backend `.env`

Do not use `http://localhost:8000` on a physical iPhone. On iPhone,
`localhost` means the iPhone itself, not your Mac or server. Use your LAN IP,
for example `http://192.168.1.50:8000`.

## Current native features

- library list from `GET /tracks`
- liked tracks from `GET /tracks/liked`
- like/unlike with `PUT` / `DELETE /tracks/{id}/like`
- torrent search through `GET /sources/piratebay/search`
- torrent import through `POST /imports/piratebay/{torrent_id}`
- direct playback from `GET /tracks/{id}/stream`
- background playback through iOS `audio` background mode
- lock screen, Control Center, headphones, and Dynamic Island media controls through `MPNowPlayingInfoCenter` and `MPRemoteCommandCenter`
- settings screen for endpoint and token

## Background audio notes

The app uses `AVAudioSession` with the `.playback` category and keeps `AVPlayer`
running when the app is backgrounded. iOS will show the native Now Playing UI on
the lock screen, in Control Center, and on supported Dynamic Island devices.

This is not a custom Live Activity. It is the standard iOS media experience,
which is the right path for music playback controls.

## Notes

The project enables App Transport Security arbitrary loads in `Info.plist` so
plain HTTP LAN backends work during development. For a public release, use HTTPS
and replace this with a narrower exception.
