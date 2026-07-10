# Mekamb Music Native Android

Native Android client for Mekamb Music. This app does not use Electron, React,
Capacitor, or a WebView. It talks directly to the FastAPI backend with
`HttpURLConnection` and streams tracks with Android `MediaPlayer`.

## Open in Android Studio

Open this directory:

```bash
native-android/
```

Then let Android Studio sync Gradle and run the `app` configuration on an
emulator or connected Android device.

## Build from the terminal

Android Studio includes a JDK. If your shell does not already have a JDK and SDK
configured, use:

```bash
cd native-android
ANDROID_HOME="$HOME/Library/Android/sdk" \
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
./gradlew :app:assembleDebug
```

The debug APK is written to:

```bash
native-android/app/build/outputs/apk/debug/app-debug.apk
```

## Connect to the backend

Start the backend first:

```bash
docker compose up --build
```

In the Android app, open Settings and enter:

- API endpoint: `YOUR_MAC_OR_SERVER_LAN_IP:8000`
- optional Prowlarr API key for indexer searches

Then sign in under **Account**: log in with your email/username and password,
migrate a legacy `API_TOKEN` (this replaces the token with your new credentials
and the old token stops working), or sign up (new accounts need admin approval).

The app automatically adds `http://` when you type only `192.168.1.50:8000`.
Do not use `localhost` on a physical Android device; it points to the device
itself. Use your Mac/server LAN IP, for example `http://192.168.1.50:8000`.

Plain HTTP traffic is enabled for private LAN development. For a public release,
use HTTPS and narrow this policy.

## Current native features

- library list from `GET /tracks`, fetched page by page
- albums tab grouped from library tracks
- liked songs from `GET /tracks/liked`
- like/unlike with `PUT` / `DELETE /tracks/{id}/like`
- source search through `GET /sources/search`
- indexer search through `GET /sources/indexers/search`
- torrent import through the matching `/imports/...` endpoint
- direct playback from `GET /tracks/{id}/stream`
- mini-player with play/pause, previous, next, and progress
- settings screen for endpoint, account login/token migration, and optional Prowlarr key
