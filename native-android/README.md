# Mekamb Music Native Android

Native Android client for Mekamb Music. This app does not use Electron, React,
Capacitor, or a WebView. The UI is Jetpack Compose; networking stays plain
`HttpURLConnection` (wrapped in suspend functions, see `data/ApiClient.kt`)
and playback is a process-scoped `android.media.MediaPlayer` singleton
(`Playback.kt`) with a foreground service for lock-screen/Bluetooth controls.

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

On launch the app shows an onboarding + login screen. Enter:

- API endpoint: `YOUR_MAC_OR_SERVER_LAN_IP:8000`

Then log in with your email/username and password, or sign up (new accounts are
`pending` and need admin approval before they can log in). Admins get an
**Approve accounts** panel under Settings → Account.

The app automatically adds `http://` when you type only `192.168.1.50:8000`.
Do not use `localhost` on a physical Android device; it points to the device
itself. Use your Mac/server LAN IP, for example `http://192.168.1.50:8000`.

Plain HTTP traffic is enabled for private LAN development. For a public release,
use HTTPS and narrow this policy.

## Current native features

- Bottom tabs: Home, Library, Add Music, Imports (with an active-import badge)
- Home: pinned Liked Songs/playlists/albums grid, daily-mix shelf, recently-added shelf
- Library: filterable (All/Playlists/Albums/Artists) flat list
- Album, Artist, Liked Songs, and Daily Mix detail screens, each with a
  playable track list and like/unlike (`PUT`/`DELETE /tracks/{id}/like`)
- Add Music: Lidarr-backed catalog search/add via `/catalog/*`
- Imports: polls `GET /imports`, cancel/retry via `/imports/{id}/cancel|retry`
- Daily mixes and recommendations from `GET /recommendations/personalized`
- Full-screen Now Playing sheet (scrubbable progress, shuffle/repeat, a
  real Up Next queue) plus a persistent mini player
- Settings: account (login/migrate-token/register), server endpoint + a
  live connection check, streaming quality + prefetch/cellular-download
  toggles, offline-download and streaming-cache storage info, app version
- Offline downloads for playback without a network connection
