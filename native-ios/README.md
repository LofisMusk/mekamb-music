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

- API endpoint: `YOUR_MAC_OR_SERVER_LAN_IP:8000`

Then sign in under **Account**: log in with your email/username and password,
migrate a legacy `API_TOKEN` (this replaces the token with your new credentials
and the old token stops working), or sign up (new accounts need admin approval).

The app automatically adds `http://` when you type only `192.168.1.50:8000`.
Use the **Test connection** button in Settings before refreshing the library.

Do not use `http://localhost:8000` on a physical iPhone. On iPhone,
`localhost` means the iPhone itself, not your Mac or server. Use your LAN IP,
for example `192.168.1.50:8000`.

If iOS asks for local network permission, allow it. The app includes
`NSLocalNetworkUsageDescription` because local LAN backend access requires that
permission on current iOS versions.

## Current native features

- library list from `GET /tracks`, fetched page-by-page so imports do not hide older albums
- albums tab grouped from library tracks by normalized album title so featured artists do not split one album into duplicates
- stable alphabetical album ordering and original album track ordering
- album detail pages with tracks in original album order when filenames contain track numbers
- album covers from `GET /tracks/{id}/artwork`, matching the browser frontend's cover.jpg behavior
- liked tracks from `GET /tracks/liked`
- like/unlike with `PUT` / `DELETE /tracks/{id}/like`
- torrent search through `GET /sources/piratebay/search`
- torrent import through `POST /imports/piratebay/{torrent_id}` with a native progress bar
- stable library refresh after imports without showing false `cancelled` errors
- direct playback from `GET /tracks/{id}/stream`
- offline downloads for individual songs and whole albums, stored on the iPhone
- removing offline downloads per song, per album, or all at once from Settings
- playback automatically uses downloaded files when the backend is offline or not configured
- expanded Spotify-like Now Playing sheet from the bottom mini-player
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
