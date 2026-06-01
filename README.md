# Mekamb Music Backend

Private FastAPI backend for a Spotify-like music library. The `personal_1337x`
provider is intentionally narrow: it searches 1337x Music results with
`py1337x`, but only returns/imports torrents whose uploader exactly matches
`PERSONAL_1337X_UPLOADER`.

## Local Setup

1. Copy `.env.example` to `.env`.
2. Set `API_TOKEN` to a long random secret.
3. Set `PERSONAL_1337X_UPLOADER` to your exact 1337x uploader name.
4. Start the stack:

```bash
docker compose up --build
```

The API listens on `http://localhost:8000`.
Open `http://localhost:8000/` for a very small browser frontend that uses the
same API token and calls the backend directly.

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
- `GET /sources/1337x/search?q=...`
- `GET /sources/piratebay/search?q=...`
- `POST /imports/1337x/{torrent_id}`
- `POST /imports/piratebay/{torrent_id}`
- `GET /imports?status=queued&limit=50&offset=0`
- `GET /imports/{id}`
- `GET /imports/{id}/tracks?limit=50&offset=0`
- `POST /imports/{id}/cancel?delete_files=true`
- `POST /imports/{id}/retry?delete_files=true`
- `GET /downloads/{id}`
- `GET /library/summary`
- `GET /tracks?q=...&artist=...&album=...&source_import_id=...&limit=50&offset=0`
- `GET /tracks/liked?limit=50&offset=0`
- `GET /tracks/recent?limit=50&offset=0`
- `GET /tracks/artists?q=...&limit=50&offset=0`
- `GET /tracks/albums?q=...&limit=50&offset=0`
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
- `GET /playlists?limit=50&offset=0`
- `POST /playlists`
- `GET /playlists/{id}`
- `PATCH /playlists/{id}`
- `DELETE /playlists/{id}`
- `POST /playlists/{id}/tracks`
- `PUT /playlists/{id}/tracks/order`
- `DELETE /playlists/{id}/tracks/{track_id}`

Pass `Authorization: Bearer <API_TOKEN>` to every non-health endpoint.

## Safety Model

- The 1337x provider is disabled unless `PERSONAL_1337X_UPLOADER` is set.
- Search results are filtered by exact uploader match.
- Import resolves the torrent with `info()` and verifies the uploader again.
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
