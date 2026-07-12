"""Fetches Internet Archive torrent content directly over HTTPS instead of via
BitTorrent, using Lidarr's "Torrent Blackhole" download client protocol as the
integration point.

Lidarr drops the grabbed .torrent file into `ia_blackhole_torrent_dir`; this
worker parses it, resolves each wanted audio file straight to its archive.org
download URL, fetches it over plain HTTPS (bypassing BitTorrent/webseed
entirely — archive.org's swarms are frequently dead or have malformed webseed
entries, but direct HTTPS from archive.org is fast and reliable), and writes
the result into `ia_blackhole_watch_dir`, which Lidarr scans as a completed
download.

Run as a background asyncio task in FastAPI (run_ia_blackhole_loop), or
standalone: python -m app.workers.ia_direct_fetch_worker
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import httpx

from app.catalog import bencode
from app.catalog.internet_archive import _AUDIO_EXTENSIONS
from app.core.config import settings

logger = logging.getLogger(__name__)

_DOWNLOAD_URL = "https://archive.org/download/{identifier}/{path}"
_MAX_ATTEMPTS = 3
_REQUEST_TIMEOUT_SECONDS = 60.0


class TorrentParseError(ValueError):
    pass


def parse_torrent(data: bytes) -> tuple[str, list[tuple[str, int]]]:
    """Returns (archive.org identifier, [(relative file path, size in bytes)])."""
    try:
        decoded = bencode.decode(data)
    except bencode.BencodeError as exc:
        raise TorrentParseError(f"invalid bencode: {exc}") from exc

    if not isinstance(decoded, dict) or b"info" not in decoded:
        raise TorrentParseError("missing 'info' dict")
    info = decoded[b"info"]
    if not isinstance(info, dict) or b"name" not in info:
        raise TorrentParseError("missing 'info.name'")

    identifier = info[b"name"].decode("utf-8", errors="replace")

    if b"files" in info:
        files_field = info[b"files"]
        if not isinstance(files_field, list):
            raise TorrentParseError("'info.files' is not a list")
        files: list[tuple[str, int]] = []
        for entry in files_field:
            if not isinstance(entry, dict) or b"path" not in entry or b"length" not in entry:
                continue
            parts = [p.decode("utf-8", errors="replace") for p in entry[b"path"]]
            files.append(("/".join(parts), int(entry[b"length"])))
        return identifier, files

    if b"length" in info:
        return identifier, [(identifier, int(info[b"length"]))]

    raise TorrentParseError("neither 'info.files' nor 'info.length' present")


def select_wanted_files(files: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Allowlist audio files only (skip cover art / spectrograms / metadata
    entirely), preferring .mp3 when present, else whichever single format has
    the most total bytes — matching InternetArchiveClient's size logic so the
    file we end up with is the one we already estimated the release's size
    from."""
    by_extension: dict[str, list[tuple[str, int]]] = {}
    for rel_path, size in files:
        lower = rel_path.lower()
        ext = next((e for e in _AUDIO_EXTENSIONS if lower.endswith(e)), None)
        if ext is None:
            continue
        by_extension.setdefault(ext, []).append((rel_path, size))

    if not by_extension:
        return []
    if ".mp3" in by_extension:
        return by_extension[".mp3"]
    return max(by_extension.values(), key=lambda group: sum(size for _, size in group))


def _looks_complete(output_dir: Path, wanted: list[tuple[str, int]]) -> bool:
    return all((output_dir / rel_path).stat().st_size == size for rel_path, size in wanted if (output_dir / rel_path).exists()) and all(
        (output_dir / rel_path).exists() for rel_path, _ in wanted
    )


async def _download_file(client: httpx.AsyncClient, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as fh:
                    async for chunk in response.aiter_bytes():
                        fh.write(chunk)
                tmp.replace(dest)
            return
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            logger.warning(
                "ia-direct-fetch download attempt %s/%s failed for %s: %s",
                attempt, _MAX_ATTEMPTS, url, exc,
            )
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(1.5 * attempt)
    raise RuntimeError(f"failed to download {url} after {_MAX_ATTEMPTS} attempts") from last_error


async def process_torrent(torrent_path: Path, watch_dir: Path) -> bool:
    """Processes a single dropped .torrent file. Returns True if the release
    was fetched (or already had been) and the source .torrent was cleaned up,
    False if it should be retried on a later pass."""
    try:
        identifier, files = parse_torrent(torrent_path.read_bytes())
    except (TorrentParseError, OSError) as exc:
        logger.error("ia-direct-fetch: could not parse %s: %s", torrent_path, exc)
        return False

    wanted = select_wanted_files(files)
    if not wanted:
        logger.warning("ia-direct-fetch: no audio files found in %s", torrent_path)
        return False

    # Lidarr correlates a completed Torrent Blackhole download with the
    # .torrent file it originally dropped by matching on that file's own
    # name (without extension) — NOT the archive.org identifier embedded
    # inside the torrent's bencode, which is usually a different string.
    # The output folder must use the .torrent's filename stem or Lidarr's
    # own periodic completion check will never recognize it as finished.
    output_dir = watch_dir / torrent_path.stem
    if output_dir.exists() and _looks_complete(output_dir, wanted):
        logger.info("ia-direct-fetch: %s already complete, cleaning up torrent file", identifier)
        torrent_path.unlink(missing_ok=True)
        return True

    output_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
        for rel_path, size in wanted:
            dest = output_dir / rel_path
            if dest.exists() and dest.stat().st_size == size:
                continue
            url = _DOWNLOAD_URL.format(
                identifier=quote(identifier),
                path="/".join(quote(part) for part in PurePosixPath(rel_path).parts),
            )
            try:
                await _download_file(client, url, dest)
            except RuntimeError as exc:
                logger.error("ia-direct-fetch: giving up on %s this pass: %s", identifier, exc)
                return False

    logger.info("ia-direct-fetch: fetched %s (%d file(s)) directly over HTTPS", identifier, len(wanted))
    torrent_path.unlink(missing_ok=True)
    return True


async def run_ia_blackhole_once() -> int:
    """Processes every pending .torrent file once. Returns how many were
    successfully fetched."""
    torrent_dir = settings.ia_blackhole_torrent_dir
    watch_dir = settings.ia_blackhole_watch_dir
    if not torrent_dir.is_dir():
        return 0

    processed = 0
    for torrent_path in sorted(torrent_dir.glob("*.torrent")):
        try:
            if await process_torrent(torrent_path, watch_dir):
                processed += 1
        except Exception:
            logger.exception("ia-direct-fetch: unexpected error processing %s", torrent_path)
    return processed


async def run_ia_blackhole_loop() -> None:
    """Infinite loop — run as a FastAPI background task."""
    if not settings.ia_blackhole_enabled:
        return
    settings.ia_blackhole_torrent_dir.mkdir(parents=True, exist_ok=True)
    settings.ia_blackhole_watch_dir.mkdir(parents=True, exist_ok=True)
    while True:
        await asyncio.sleep(settings.ia_blackhole_poll_interval_seconds)
        try:
            processed = await run_ia_blackhole_once()
            if processed:
                logger.info("ia-direct-fetch loop: processed %d release(s)", processed)
        except Exception:
            logger.exception("ia-direct-fetch loop error")


async def _main() -> None:
    processed = await run_ia_blackhole_once()
    print(f"processed {processed} release(s)")


if __name__ == "__main__":
    asyncio.run(_main())
