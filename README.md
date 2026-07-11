# Mekamb Music Backend

Private FastAPI backend for a Spotify-like music library. A shared catalog is
grown through **Lidarr**: any approved user requests an artist/album via
`/catalog`, Lidarr (with its own Prowlarr + download client) acquires and
organizes it, and the backend ingests the finished album into a persistent local
library through its quarantine → validation → storage pipeline. Each user can
also build personal **libraries** — named subsets of the shared catalog. Clients
stream everything from this backend.

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
deploy target should verify database, auth configuration, sandbox directories,
Redis, and (when `LIDARR_ENABLED=true`) Lidarr reachability before routing traffic.
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
- `GET /catalog/search?kind=artist|album&q=...`
- `POST /catalog/add`
- `GET /catalog/requests`
- `POST /catalog/webhook` (called by Lidarr, shared-secret token)
- `GET /imports?status=queued&limit=50&offset=0`
- `GET /imports/{id}`
- `GET /imports/{id}/tracks?limit=50&offset=0`
- `POST /imports/{id}/cancel?delete_files=true`
- `POST /imports/{id}/retry?delete_files=true`
- `GET /libraries?limit=50&offset=0`
- `POST /libraries`
- `GET /libraries/{id}`
- `GET /libraries/{id}/tracks`
- `PATCH /libraries/{id}`
- `DELETE /libraries/{id}`
- `POST /libraries/{id}/tracks`
- `DELETE /libraries/{id}/tracks/{track_id}`
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

`/recommendations/tracks/{track_id}` returns Spotify-like recommendations from
tracks already in the shared catalog. The score uses artist, album, title token
overlap, duration proximity, likes, recent playback seeds, and cross-user
collaborative filtering. `/recommendations/library` builds a broader seed set
from liked tracks, recent plays, and latest imports. Recommendations no longer
fetch external torrent candidates; to add something missing to the catalog, use
`POST /catalog/add` and let Lidarr acquire it.

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

- Acquisition is delegated to Lidarr; the backend never talks to a download
  client directly. `POST /catalog/add` (any approved user) tells Lidarr to
  monitor + search for an artist/album.
- When Lidarr finishes importing an album it calls `POST /catalog/webhook`
  (verified by the shared `LIDARR_WEBHOOK_TOKEN`). The backend copies/hardlinks
  the finished album from Lidarr's root folder into a per-import quarantine
  directory and queues an ingest job (`source=lidarr`).
- The worker imports only allowed audio extensions from quarantine. If the folder
  has no supported audio files or its quarantine path is missing/invalid, the
  import is marked `failed` instead of staying active.
- Quarantine paths are sandbox-checked: they must live under `QUARANTINE_ROOT` and
  never inside `LIBRARY_ROOT`. Cleanup refuses any path outside the quarantine root.
- Redis is only a wake-up signal for the worker; Postgres remains the source of
  truth for import state.
- After a successful import the worker cleans the quarantine directory by default.
  Set `CLEANUP_QUARANTINE_AFTER_IMPORT=false` to inspect ingested files.
- Original files are preserved; FLAC/ALAC stay lossless and MP3 stays MP3.

## Configuration Notes

- `LIDARR_URL` / `LIDARR_API_KEY` point the backend at Lidarr for artist/album
  lookup and add (`X-Api-Key`). `LIDARR_ENABLED=true` makes `/health/ready` verify
  Lidarr is reachable.
- Lidarr/Prowlarr WebUI auth is configured by the `servarr-auth-init` compose
  service before the apps start. It reads `SERVARR_WEBUI_USERNAME` /
  `SERVARR_WEBUI_PASSWORD` from `.env` (or the `LIDARR_` / `PROWLARR_` per-app
  overrides), writes the `LIDARR_AUTH_*` / `PROWLARR_AUTH_*` settings to
  `config.xml`, pins `LIDARR_API_KEY` / `PROWLARR_API_KEY`, and stores the WebUI
  password as the Servarr PBKDF2 hash in each app's SQLite `Users` table.
- `LIDARR_ROOT_FOLDER` is Lidarr's organized-output path. It must be mounted at the
  **same path** in both the Lidarr container and the API/worker containers so the
  webhook's track-file paths resolve on the backend side.
- `LIDARR_QUALITY_PROFILE_ID` / `LIDARR_METADATA_PROFILE_ID` are the Lidarr profile
  ids used when adding an artist/album.
- `LIDARR_WEBHOOK_TOKEN` is the shared secret; configure Lidarr's Connect → Webhook
  as `http://api:8000/catalog/webhook?token=<token>` on the import events.
- `LIDARR_INGEST_STRATEGY` is `copy` or `hardlink` (hardlink avoids duplicating
  large lossless files when the root folder and quarantine share a filesystem).
- `QUARANTINE_ROOT` is the path seen by API/worker containers.
- `LIBRARY_ROOT` must never point inside quarantine, and quarantine must never
  point inside the library.
- `STORAGE_BACKEND=local` keeps only the streamable local cache.
- `STORAGE_BACKEND=s3` keeps the same local cache for Range streaming and also
  mirrors imported originals into the configured S3/MinIO bucket.
- Lidarr's own torrenting (its download client's listen port, indexers, etc.) is
  configured inside Lidarr/qBittorrent, not the backend. On a Linux server, open
  the download client's TCP/UDP port in the host firewall and any VPS/cloud
  security group so grabs don't stall.
- The API, worker, and Lidarr containers share the `library-source` volume as
  UID/GID `1000`. The `volume-init` service fixes named-volume ownership before
  the app starts so the worker can read Lidarr's organized albums.

## Deezer via Lidarr (deemix branch)

This branch adds **Deezer** as a music source using the
[`TrevTV/Lidarr.Plugin.Deezer`](https://github.com/TrevTV/Lidarr.Plugin.Deezer)
plugin, so albums can be pulled straight from Deezer (FLAC/MP3) instead of only
torrents. It's wired so the rest of the stack doesn't change:

- **Lidarr runs the plugins image** — `lscr.io/linuxserver/lidarr:nightly` in
  [docker-compose.yml](docker-compose.yml). ⚠️ Switching to `nightly` runs a
  one-way Lidarr DB migration; you can't move back to a mainline image without
  restoring a pre-nightly `lidarr-config` backup.
- **`lidarr-deezer-init`** (one-shot compose job, [scripts/configure_lidarr_deezer.py](scripts/configure_lidarr_deezer.py))
  waits for Lidarr, installs the Deezer plugin via its API, restarts Lidarr to
  load it, then adds a Deezer **indexer** + **download client** — discovering the
  plugin's field names from Lidarr's live schemas and injecting `DEEZER_ARL`. It's
  idempotent, so it no-ops on every subsequent `docker compose up`.
- **`DEEZER_ARL`** is optional: leave it blank and the plugin auto-picks a token;
  set your own Deezer ARL (premium account for FLAC) for reliability.
  `DEEZER_PLUGIN_URL` / `DEEZER_DOWNLOAD_DIR` are advanced overrides.
- **Nothing else changes.** Deezer is just another indexer/download client inside
  Lidarr, so the backend `/catalog` flow and the native apps are unaffected —
  searching an artist in the app and tapping **Add** now grabs it from Deezer via
  Lidarr with no app-side change. qBittorrent + Prowlarr stay wired for torrents
  too, and Lidarr picks whichever source satisfies the quality profile.
