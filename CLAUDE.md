# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A private, self-hosted Spotify-like music service. The shared catalog is grown
through **Lidarr** (which owns discovery/monitoring/downloading via its own
Prowlarr + download client); the FastAPI backend ingests finished albums into a
persistent local library and streams them to native clients. There is **no
browser frontend** — clients are the native iOS, Android, and desktop apps in
`native-*/`, which talk directly to the backend over HTTP + bearer auth.

Read `README.md` for the full product/ops story (Lidarr wiring, safety model,
sync, Internet Archive proxy). This file covers how to work in the code.

## Commands

Backend (Python 3.11+, run from repo root):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'      # install with dev extras (pytest, aiosqlite)

pytest -q                    # run the full suite (tests/ use aiosqlite, no live services)
pytest tests/test_import_worker.py -q          # one file
pytest tests/test_import_worker.py::test_name  # one test
ruff check .                 # lint (config in pyproject.toml, line-length 100)

python -m app.api.openapi_export openapi.json  # export OpenAPI schema for clients
```

Full stack (Postgres + Redis + MinIO + Lidarr + qBittorrent + Prowlarr + API + worker):

```bash
docker compose up --build    # API on http://localhost:8000
```

Native clients:

```bash
open native-ios/MekambMusicNative.xcodeproj          # SwiftUI, URLSession + AVPlayer
open -a "Android Studio" native-android              # or: cd native-android && ./gradlew :app:assembleDebug
cd native-desktop && ./gradlew :native-mac:run       # Compose Multiplatform; use the module for your OS
```

## Backend architecture

FastAPI app assembled in `app/main.py`: routers are mounted under `/auth`,
`/admin`, `/catalog`, `/sync`, `/imports`, `/recommendations`, `/tracks`,
`/playback`, `/playlists`, `/libraries`, `/library`, `/torznab`.

**Layering (consistent across domains).** Each domain folder follows the same
shape — `domain.py` (protocols/dataclasses), `repository.py` (SQLAlchemy impl),
`service.py` (business logic). HTTP routes live in `app/api/routes/*.py` and get
their services/repositories wired through FastAPI dependencies in
`app/api/deps.py`. When adding an endpoint, follow this: put logic in a service,
persistence in a repository, and wire it in `deps.py` — don't put DB queries in
route handlers.

**Auth (`app/api/deps.py`, `app/core/auth.py`, `app/auth/`).** Session tokens
from `/auth/login` are the only scheme — there is no raw `API_TOKEN` bearer auth.
A token resolves (via `resolve_session_token`) to an *approved* `User`; pending/
rejected/disabled accounts never resolve. Self-signup (`/auth/register`) creates
a `pending` account that an admin must approve (`/admin/users/*`); emails in
`ADMIN_EMAILS` are bootstrapped as approved admins. Every protected request
resolves to an `api_key_id` data scope. Shared data (catalog, imports, storage,
libraries) is common across all identities; personal data (likes, plays,
recommendations, playback state, playlists, sync actions) is scoped per
`api_key_id`.

**Import pipeline (`app/imports/`, `app/workers/import_worker.py`).** Lidarr
finishes an album → calls `POST /catalog/webhook` (verified by
`LIDARR_WEBHOOK_TOKEN`) → backend copies/hardlinks the album into a per-import
**quarantine** dir and queues an ingest job. The separate `worker` container
(`python -m app.workers.import_worker`) picks it up, imports allowed audio
extensions from quarantine into the library, extracts tags/cover, and stores.
Postgres is the source of truth for import state; **Redis is only a wake-up
signal** — the worker also polls as a fallback. Quarantine paths are
sandbox-checked (`app/core/runtime.py`): they must live under `QUARANTINE_ROOT`
and never inside `LIBRARY_ROOT`, enforced at startup.

**Background loops.** The API process runs in-process asyncio background tasks
(started in `main.py` lifespan): cache TTL cleanup, audio-feature extraction,
collaborative-filtering recompute, and the IA direct-fetch (Torrent Blackhole
fallback) loop. The heavy import ingest runs in the *separate* worker container.

**Storage (`app/storage/`).** `STORAGE_BACKEND=local` keeps only a streamable
local cache; `s3` additionally mirrors originals to S3/MinIO. `app/library/`
handles audio scanning, transcoding (lossless → AAC via ffmpeg), Range
streaming, and prefetch of upcoming queue tracks.

**Recommendations (`app/recommendations/`).** Scores use artist/album/title
token overlap, duration, likes, recent-play seeds, and cross-user collaborative
filtering — sourced only from the existing catalog (no external fetching).
Optional Gemini enrichment gated by `recommendation_use_gemini`.

**Instance sync (`app/sync/`).** Backends record user actions in `user_actions`
and reconcile via `/sync/*`. Set `INSTANCE_ID` uniquely per running backend.

**Internet Archive (`app/catalog/internet_archive.py`,
`app/api/routes/torznab.py`).** A Torznab proxy Prowlarr indexes as Generic
Torznab, plus a direct-HTTP fetch worker that bypasses flaky BitTorrent by
downloading archive.org audio over HTTPS into a folder Lidarr scans.

## Database

SQLAlchemy 2.0 async models in `app/db/models.py`. Migrations in `alembic/`
(`sqlalchemy.url` overridden by `DATABASE_URL` in practice). Note: `init_db()`
in `app/db/session.py` calls `Base.metadata.create_all` on startup, so new
tables/columns appear at runtime — but still add an Alembic migration
(`alembic/versions/NNNN_*.py`, sequentially numbered) for schema changes so
deployed instances upgrade cleanly. Tests run against aiosqlite, so keep new
model/column types SQLite-compatible.

## Configuration

All settings are in `app/core/config.py` (pydantic-settings, loaded from `.env`;
see `.env.example`). Key ones: `LIDARR_*` (acquisition + webhook), `STORAGE_BACKEND`,
`QUARANTINE_ROOT`/`LIBRARY_ROOT` (must not nest), `TORZNAB_IA_API_KEY`,
`IA_BLACKHOLE_*`, `ADMIN_EMAILS` (bootstrap admins). In docker-compose,
`LIDARR_ROOT_FOLDER` must be mounted at the **same path** in the Lidarr and
API/worker containers so webhook track-file paths resolve on both sides.

See `CLAUDE.local.md` (gitignored) for live-deployment access details.

## Notes

- Comments and log messages in the codebase are frequently in Polish; match the
  surrounding language when editing a file.
- The verification memory: LuLu firewall can block live backend calls from the
  iOS Simulator — verify backend behavior with `curl` rather than the simulator.
