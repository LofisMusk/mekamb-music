# Mekamb Music Backend

Private FastAPI backend for a Spotify-like music library. It searches music
torrents from 1337x with `py1337x` and Pirate Bay through the configured API,
then imports completed audio files into a persistent local library.

## Local Setup

1. Copy `.env.example` to `.env`.
2. Set `API_TOKEN` to a long random secret, or set `API_TOKENS` to multiple
   named secrets such as `alice:secret-one,bob:secret-two`.
3. Start the stack:

```bash
docker compose up --build
```

The API listens on `http://localhost:8000`. Clients are the native mobile and
desktop apps; there is no browser frontend.

## Accounts

Users authenticate with email/username + password. Register via
`POST /auth/register` (new accounts are `pending` and cannot log in until an
admin approves them), then `POST /auth/login` with either the email or username.
Emails in `ADMIN_EMAILS` are bootstrapped as approved admins so the first admin
can get in; admins approve/reject/disable accounts under `/admin/users`.

Existing token-based users migrate without losing data via
`POST /auth/claim-token` (the "I have a token" flow): supplying a valid
`API_TOKEN(S)` value creates an approved account that inherits that token's data
scope, so the library, liked songs, plays, playlists and playback all carry over.
An unclaimed raw API token keeps authenticating, so nobody is forced to migrate
on a deadline — but the moment a token is claimed it stops working everywhere
(requests with it get a 401 with code `token_migrated`) and the account's
email/username/password fully replaces it. Every app (iOS, Android, desktop)
has this flow in Settings under Account: log in, migrate a token, or sign up.

## Native iOS App

A native SwiftUI iPhone client lives in `native-ios/`. It does not use Electron,
Capacitor, React, Vite, or a WebView. It talks directly to the FastAPI backend
with `URLSession` and streams tracks with `AVPlayer`.

Open it with:

```bash
open native-ios/MekambMusicNative.xcodeproj
```

In the app Settings screen, set the backend endpoint, then log in (or migrate a
legacy API token / sign up) under Account. For a physical iPhone, do not use
`localhost`; use your Mac/server LAN IP, for example `http://192.168.1.50:8000`.

## Native Android App

A native Android client lives in `native-android/`. It does not use Electron,
React, Capacitor, or a WebView. It talks directly to the FastAPI backend and
streams tracks with Android `MediaPlayer`.

Open it in Android Studio:

```bash
open -a "Android Studio" native-android
```

Or build the debug APK from the terminal:

```bash
cd native-android
ANDROID_HOME="$HOME/Library/Android/sdk" \
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
./gradlew :app:assembleDebug
```

The APK is written to `native-android/app/build/outputs/apk/debug/app-debug.apk`.
On a physical Android phone, use your Mac/server LAN IP for the API endpoint,
not `localhost`.

Compose waits for Postgres and Redis healthchecks before starting the app.
MinIO readiness is handled by `minio-init`, which waits for MinIO and creates
the configured bucket before API/worker containers continue.
Use `/health` for a simple process liveness check and `/health/ready` when a
deploy target should verify database, auth/source configuration, and sandbox
directories, Redis, and qBittorrent before routing traffic.
Imports are stored in Postgres and also publish a Redis queue event so the
worker wakes up quickly; the worker still periodically scans active imports as a
fallback.

For local Python-only checks:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

To export an OpenAPI schema for a future mobile/web client:

```bash
python -m app.api.openapi_export openapi.json
```

## API

- `GET /health`
- `GET /health/ready`
- `GET /sources/search?q=...`
- `GET /sources/indexers/search?q=...`
- `GET /sources/1337x/search?q=...`
- `GET /sources/piratebay/search?q=...`
- `POST /imports/1337x/{torrent_id}`
- `POST /imports/indexer`
- `POST /imports/piratebay/{torrent_id}`
- `GET /imports?status=queued&limit=50&offset=0`
- `GET /imports/{id}`
- `GET /imports/{id}/tracks?limit=50&offset=0`
- `POST /imports/{id}/cancel?delete_files=true`
- `POST /imports/{id}/retry?delete_files=true`
- `GET /downloads/{id}`
- `GET /library/summary`
- `GET /sync/actions?since=...&include_applied=true&limit=200`
- `POST /sync/actions`
- `POST /sync/apply`
- `POST /sync/actions/{id}/apply`
- `GET /sync/imports/{info_hash}/tracks`
- `GET /sync/tracks/{track_id}/file`
- `GET /recommendations/tracks/{track_id}`
- `POST /recommendations/tracks/{track_id}/import-missing`
- `GET /recommendations/library`
- `POST /recommendations/library/import-missing`
- `GET /tracks?q=...&artist=...&album=...&source_import_id=...&limit=50&offset=0`
- `GET /tracks/liked?limit=50&offset=0`
- `GET /tracks/recent?limit=50&offset=0`
- `GET /tracks/artists?q=...&limit=50`
- `GET /tracks/albums?q=...&limit=50`
- `GET /tracks/{id}`
- `GET /tracks/{id}/stats`
- `PATCH /tracks/{id}`
- `PUT /tracks/{id}/like`
- `DELETE /tracks/{id}/like`
- `POST /tracks/{id}/plays`
- `DELETE /tracks/{id}?delete_file=true`
- `GET /tracks/{id}/artwork`
- `HEAD /tracks/{id}/stream`
- `GET /tracks/{id}/stream`
- `GET /playback/state`
- `PUT /playback/state`
- `DELETE /playback/state`
- `GET /playlists?limit=50&offset=0`
- `POST /playlists`
- `GET /playlists/{id}`
- `PATCH /playlists/{id}`
- `DELETE /playlists/{id}`
- `POST /playlists/{id}/tracks`
- `PUT /playlists/{id}/tracks/order`
- `DELETE /playlists/{id}/tracks/{track_id}`

Pass `Authorization: Bearer <API_TOKEN>` to every non-health endpoint. When
`API_TOKENS` is configured, all keys share the same downloaded albums/library,
imports, and storage, but each key has separate liked tracks, recent plays,
personalized recommendations, playback state, playlists, and sync actions.

## Recommendations

`/recommendations/tracks/{track_id}` returns Spotify-like recommendations in two
layers: local similar tracks already in the library and external candidates from
configured music sources. The local score uses artist, album, title token overlap,
duration proximity, likes, and recent playback seeds. `/recommendations/library`
builds a broader seed set from liked tracks, recent plays, and latest imports.

`POST /recommendations/.../import-missing` imports top-ranked missing external
candidates through the same import pipeline as manual searches: qBittorrent,
quarantine, audio validation, and library storage. Defaults are controlled by
`RECOMMENDATION_SOURCES`, `RECOMMENDATION_AUTO_IMPORT_LIMIT`, and
`RECOMMENDATION_MIN_SEEDERS`.

## Instance Sync

Set `INSTANCE_ID` differently for each running backend, for example `local-mac`,
`home-server`, or `cloud`. The backend records user actions in `user_actions`:
torrent imports, likes/unlikes, and track deletions.

Other instances can pull `GET /sync/actions`, push missing items with
`POST /sync/actions`, then run `POST /sync/apply`. Imported torrent actions carry
`source`, `torrent_id`, `info_hash`, `magnet_link`, `uploader`, and `source_url`,
so a second instance can reproduce the import through the same sandboxed torrent
flow. The recorded sync strategy is `peer_copy`, `remote_storage`, then `magnet`;
v1 records the strategy and exposes peer-copy helper endpoints:
`GET /sync/imports/{info_hash}/tracks` returns the tracks that came from a
completed import on this instance, and `GET /sync/tracks/{track_id}/file`
downloads a cached/restored audio file from that peer. The automatic peer client
can use those endpoints first and fall back to the saved magnet link when no peer
has the album.

`/playback/state` stores the cross-session player snapshot for the private user:
current track, playback position, playing/paused state, repeat/shuffle, active
device, and the upcoming queue. A frontend should `GET` it on startup and `PUT`
it whenever the current track, queue, or progress changes.

When the frontend saves playback state, the backend prefetches the first
`PLAYBACK_PREFETCH_COUNT` queued tracks into the local streaming cache. Streaming
also refreshes the next queued tracks in the background, so skipping from the
current song into the next album/queue item does not have to wait on remote
storage.

## Safety Model

- `/sources/search` runs a unified music search across configured torrent sources,
  tries normalized artist/title query variants, deduplicates results, and keeps
  working when one source is temporarily blocked/unavailable.
- `/sources/indexers/search` queries configured Torznab/Prowlarr music indexers
  and returns importable magnet-backed results. The app still imports through this
  backend, qBittorrent, and the quarantine/library pipeline.
- 1337x searches are limited to Music category results and sorted by seeders by default.
- Import resolves the torrent with `info()` before enqueueing it.
- qBittorrent only receives the quarantine volume, never the library volume.
- The worker waits until qBittorrent reports the torrent as complete, then imports
  only allowed audio extensions from quarantine.
- If the completed torrent has no supported audio files or its quarantine path is
  missing/invalid, the import is marked `failed` instead of staying active.
- Before importing, the worker verifies that qBittorrent reports the expected
  `info_hash` and the exact per-import download path.
- Redis is only a wake-up signal for the worker; Postgres remains the source of
  truth for import state.
- After a successful import, the worker removes the completed torrent and cleans
  its quarantine directory by default. Set `REMOVE_TORRENT_AFTER_IMPORT=false` or
  `CLEANUP_QUARANTINE_AFTER_IMPORT=false` if you want to inspect downloaded files.
- Original files are preserved; FLAC/ALAC stay lossless and MP3 stays MP3.
- The v1 1337x API surface intentionally has no trending/top/browse endpoints.
- Pirate Bay imports use the configured category but do not require a title marker.

## Configuration Notes

- `QUARANTINE_ROOT` is the path seen by API/worker containers.
- `TORRENT_DOWNLOAD_ROOT` is the path sent to qBittorrent over RPC.
- `MUSIC_INDEXER_PROWLARR_URL` points at the Prowlarr service, for example
  `http://prowlarr:9696`; the backend queries `/api/v1/search` across configured
  Prowlarr indexers.
- `MUSIC_INDEXER_TORZNAB_URLS` can contain one or more raw Torznab/Prowlarr URLs,
  separated by commas or newlines, if you prefer per-indexer URLs.
- `MUSIC_INDEXER_API_KEY` is used as Prowlarr's `X-Api-Key` header and as
  `apikey` for raw Torznab URLs.
- `MUSIC_INDEXER_CATEGORIES` defaults to `3000` for audio/music Torznab searches.
- `RECOMMENDATION_SOURCES` is a comma-separated list used by recommendation
  search/import, defaulting to `indexer`. Set `indexer,1337x,piratebay` only if
  those sources are intentionally allowed for automatic recommendation imports.
- `RECOMMENDATION_AUTO_IMPORT_LIMIT` and `RECOMMENDATION_MIN_SEEDERS` control how
  many missing recommendations can be queued by one request and the minimum
  seeders needed before an external candidate is imported.
- In Docker Compose both paths point to the same named volume, mounted at different
  container paths, so qBittorrent can write downloads while the worker scans them.
- `LIBRARY_ROOT` must never point inside quarantine, and quarantine must never
  point inside the library.
- `STORAGE_BACKEND=local` keeps only the streamable local cache.
- `STORAGE_BACKEND=s3` keeps the same local cache for Range streaming and also
  mirrors imported originals into the configured S3/MinIO bucket.
- `TORRENT_LISTEN_PORT` is used by the app, qBittorrent, and Docker's TCP/UDP
  port mappings. On a Linux server, also open this port for both TCP and UDP in
  the host firewall and any VPS/cloud security group; otherwise torrents may stay
  stalled even when the WebUI works.
- The API, worker, and qBittorrent containers share the quarantine volume as
  UID/GID `1000`. The `volume-init` service fixes named-volume ownership before
  the app starts so qBittorrent can write into per-import download directories.
