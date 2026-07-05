# Mekamb Music — Desktop (Compose Multiplatform)

Native desktop client (no Electron) for macOS, Linux and Windows, built with
Kotlin + Compose for Desktop. One shared codebase (`shared/`), three thin
platform modules living at the repo root: `../native-mac`, `../native-linux`,
`../native-windows` (packaging, icons and per-OS ffmpeg natives).

## Development

Requires JDK 21. All commands run from this directory:

```bash
./gradlew :native-mac:run        # run the app (use the module matching your OS)
./gradlew build                  # compile everything + run shared tests
./gradlew :native-mac:packageDmg # local installer build (host OS only)
```

Audio playback uses bundled ffmpeg (bytedeco) → decodes mp3/flac/m4a/ogg/opus/wav
with no system dependencies. Streaming hits the backend `/tracks/{id}/stream`
endpoint with bearer auth; offline downloads and the playback prefetch cache are
stored under the per-OS app data/cache directories.

## Releases & auto-update

Pushing a `v*` tag triggers `.github/workflows/release.yml`, which builds the
`.dmg` / `.deb` + `.AppImage` / `.msi` (plus the mobile apps) into a single
GitHub Release with `SHA256SUMS.txt`. The apps check GitHub Releases on startup
(and on demand in Settings) and offer to download + install newer versions.
