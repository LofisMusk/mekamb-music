"""Direct-push Internet Archive backfill.

Instead of relying on Lidarr to search Prowlarr, parse a messy archive.org title
into a grabbable release, and route a (usually dead) torrent — every step of
which is flaky — this worker pushes content the other way:

  1. ask Lidarr which monitored albums are still missing,
  2. find each one directly on archive.org (global audio search, scored so we
     pick the right item out of the noise),
  3. download the audio over plain HTTPS into a staging folder Lidarr can see, and
  4. import it into the library via Lidarr's Manual Import API.

No Prowlarr, no BitTorrent, no download client. Lidarr still owns organizing,
metadata and the post-import webhook that feeds the backend's own ingest.

Run as a FastAPI background task (run_ia_backfill_loop) or standalone:
    python -m app.workers.ia_backfill_worker
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import httpx
from redis.asyncio import Redis

from app.catalog import ia_import
from app.catalog.internet_archive import _AUDIO_EXTENSIONS, InternetArchiveClient
from app.catalog.lidarr_client import LidarrClient, LidarrError
from app.core.config import settings
from app.imports.lidarr_reconcile import ingest_lidarr_album
from app.imports.queue import RedisImportQueue

logger = logging.getLogger(__name__)

# archive.org bundles a whole item into one zip of a single derived format on the
# fly ("Otwórz .../compress/<id>/formats=VBR MP3&file=/<id>.zip"). We grab the
# album in one request instead of fetching each track; the endpoint can be slow
# to start streaming while it builds the zip, so give the read a long leash.
_COMPRESS_URL = "https://archive.org/compress/{identifier}/formats={fmt}&file=/{identifier}.zip"
_GRAB_TIMEOUT = httpx.Timeout(60.0, read=300.0)
_COOLDOWN_KEY = "mekamb-music:ia-backfill:cooldown:{album_id}"


def _extract_audio(zip_path: Path, output_dir: Path) -> list[str]:
    """Extract just the audio entries of a downloaded /compress/ zip into
    output_dir (flattened), returning their basenames."""
    extracted: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = PurePosixPath(info.filename).name
            if not name.lower().endswith(_AUDIO_EXTENSIONS):
                continue
            with zf.open(info) as src, open(output_dir / name, "wb") as out:
                shutil.copyfileobj(src, out)
            extracted.append(name)
    return extracted


async def _grab_release(identifier: str, fmt: str, output_dir: Path) -> list[str]:
    """Download the whole item as a single archive.org /compress/ zip (one
    derived format) and extract the audio into output_dir. Returns the extracted
    filenames, or [] if the download failed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    url = _COMPRESS_URL.format(identifier=quote(identifier), fmt=quote(fmt))
    tmp_zip = output_dir.parent / f"{output_dir.name}.zip.part"
    try:
        async with httpx.AsyncClient(timeout=_GRAB_TIMEOUT, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with open(tmp_zip, "wb") as fh:
                    async for chunk in response.aiter_bytes():
                        fh.write(chunk)
        return await asyncio.to_thread(_extract_audio, tmp_zip, output_dir)
    except (httpx.HTTPError, zipfile.BadZipFile, OSError) as exc:
        logger.error("ia-backfill: grab failed for %s (%s): %s", identifier, fmt, exc)
        return []
    finally:
        tmp_zip.unlink(missing_ok=True)


def _import_into_lidarr(
    lidarr: LidarrClient,
    *,
    album: dict,
    artist_id: int,
    album_dir: Path,
) -> int:
    """Synchronous Lidarr side of one album (run via asyncio.to_thread). Returns
    the number of files handed to ManualImport, or 0 if nothing could be mapped."""
    album_id = int(album["id"])
    release_id = ia_import.monitored_release_id(lidarr.get_album(album_id))
    if release_id is None:
        logger.warning("ia-backfill: no album release for album %s, skipping import", album_id)
        return 0

    tracks = lidarr.album_tracks(album_release_id=release_id)
    candidates = lidarr.manual_import_candidates(
        str(album_dir), artist_id=artist_id, album_id=album_id
    )
    file_quality_pairs = [(str(c["path"]), c.get("quality")) for c in candidates if c.get("path")]
    files = ia_import.build_manual_import_files(
        file_quality_pairs,
        tracks,
        artist_id=artist_id,
        album_id=album_id,
        album_release_id=release_id,
    )
    if not files:
        logger.warning(
            "ia-backfill: could not map any of the %d file(s) in %s to album %s (release %s, %d tracks)",
            len(file_quality_pairs), album_dir, album_id, release_id, len(tracks),
        )
        return 0

    lidarr.run_manual_import(files, import_mode=settings.ia_backfill_import_mode)
    return len(files)


async def _process_album(album: dict, ia: InternetArchiveClient, lidarr: LidarrClient) -> bool:
    artist = album.get("artist") or {}
    artist_name = str(artist.get("artistName") or "").strip()
    album_title = str(album.get("title") or "").strip()
    artist_id = album.get("artistId") or artist.get("id")
    if not artist_name or not album_title or not artist_id:
        return False

    docs = await ia.search_audio_items(artist_name, album_title)
    ranked = ia_import.rank_candidates(artist_name, album_title, docs)
    best = next((c for c in ranked if c.score >= settings.ia_backfill_min_match_score), None)
    if best is None:
        logger.info("ia-backfill: no archive.org match for %s – %s", artist_name, album_title)
        return False

    fmt = ia_import.select_audio_format(await ia.item_formats(best.identifier))
    if fmt is None:
        logger.info("ia-backfill: %s has no downloadable audio format", best.identifier)
        return False

    logger.info(
        "ia-backfill: matched %s – %s to %s (score %.2f, format %s)",
        artist_name, album_title, best.identifier, best.score, fmt,
    )
    album_dir = settings.ia_backfill_staging_dir / ia_import.staging_folder_name(artist_name, album_title)
    extracted = await _grab_release(best.identifier, fmt, album_dir)
    if not extracted:
        logger.warning("ia-backfill: grabbed no audio for %s", best.identifier)
        return False
    logger.info("ia-backfill: grabbed %d track(s) for %s", len(extracted), best.identifier)

    imported = await asyncio.to_thread(
        _import_into_lidarr, lidarr, album=album, artist_id=int(artist_id), album_dir=album_dir
    )
    return imported > 0


async def run_ia_backfill_once() -> int:
    """One pass: import up to ``ia_backfill_max_albums_per_pass`` missing albums.
    Returns how many were handed to Lidarr for import."""
    lidarr = LidarrClient.from_settings(settings)
    if not lidarr.configured:
        return 0

    ia = InternetArchiveClient(redis_url=settings.redis_url)
    redis: Redis = ia._redis  # reuse the same connection for cooldown bookkeeping
    publisher = RedisImportQueue.from_settings(settings)
    settings.ia_backfill_staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        missing = await asyncio.to_thread(lidarr.missing_albums)
    except LidarrError as exc:
        logger.warning("ia-backfill: could not list missing albums: %s", exc)
        await ia.close()
        await publisher.close()
        return 0

    processed = 0
    imported = 0
    for album in missing:
        # Cap on albums *attempted* per pass, not imported — otherwise a pass
        # where every import fails would churn through the entire missing list,
        # downloading everything at once. The per-album cooldown means the next
        # pass picks up where this one left off.
        if processed >= settings.ia_backfill_max_albums_per_pass:
            break
        album_id = album.get("id")
        if not album_id:
            continue
        cooldown_key = _COOLDOWN_KEY.format(album_id=album_id)
        if await redis.get(cooldown_key):
            continue
        # Set the cooldown up front so a crash mid-album doesn't re-hammer
        # archive.org/Lidarr every pass; it expires so genuine failures retry.
        await redis.set(cooldown_key, "1", ex=settings.ia_backfill_retry_cooldown_seconds)
        processed += 1
        try:
            if await _process_album(album, ia, lidarr):
                imported += 1
                # Don't re-grab a whole album every hour to chase tracks the
                # archive doesn't have; back off hard once it's imported.
                await redis.set(
                    cooldown_key, "1", ex=settings.ia_backfill_success_cooldown_seconds
                )
                # Push it straight into the app (Manual Import doesn't fire
                # Lidarr's webhook); the reconcile loop is the backstop.
                try:
                    await ingest_lidarr_album(lidarr, album, publisher=publisher, wait_seconds=20)
                except Exception:
                    logger.exception("ia-backfill: app ingest failed for album %s", album_id)
        except LidarrError as exc:
            logger.warning("ia-backfill: Lidarr import failed for album %s: %s", album_id, exc)
        except Exception:
            logger.exception("ia-backfill: unexpected error processing album %s", album_id)

    await ia.close()
    await publisher.close()
    return imported


async def run_ia_backfill_loop() -> None:
    """Infinite loop — run as a FastAPI background task."""
    if not settings.ia_backfill_enabled:
        return
    settings.ia_backfill_staging_dir.mkdir(parents=True, exist_ok=True)
    while True:
        await asyncio.sleep(settings.ia_backfill_poll_interval_seconds)
        try:
            imported = await run_ia_backfill_once()
            if imported:
                logger.info("ia-backfill loop: imported %d album(s)", imported)
        except Exception:
            logger.exception("ia-backfill loop error")


async def _main() -> None:
    imported = await run_ia_backfill_once()
    print(f"imported {imported} album(s)")


if __name__ == "__main__":
    asyncio.run(_main())
