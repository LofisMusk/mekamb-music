"""On-demand lossless → AAC transcoding for the "AAC" / "Auto" playback quality.

The client requests `?format=aac` on the stream endpoint; for lossless sources (FLAC, WAV,
AIFF, …) we transcode once to an AAC-in-MP4 file cached on disk and serve that. Already-lossy
sources (MP3, AAC) are left untouched — re-encoding lossy audio only loses quality without saving
meaningful bandwidth. ffmpeg is provided by the runtime image (see Dockerfile); if it is missing
or fails, callers fall back to streaming the original file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

# Lossless / uncompressed containers worth shrinking to AAC when the client asks for it.
LOSSLESS_EXTENSIONS = {".flac", ".wav", ".wave", ".aif", ".aiff", ".alac", ".ape", ".wv"}
LOSSLESS_MEDIA_TYPES = {
    "audio/flac",
    "audio/x-flac",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/aiff",
    "audio/x-aiff",
}

# AAC-in-MP4 is what we emit; players negotiate it as audio/mp4.
AAC_MEDIA_TYPE = "audio/mp4"


class TranscodeUnavailable(RuntimeError):
    """Raised when transcoding cannot be performed (no ffmpeg, or the encode failed)."""


def is_lossless_source(path: Path, media_type: str | None) -> bool:
    """True when the source is a lossless format that benefits from AAC transcoding."""
    if path.suffix.lower() in LOSSLESS_EXTENSIONS:
        return True
    return (media_type or "").lower() in LOSSLESS_MEDIA_TYPES


def transcode_to_aac(source: Path, *, track_id: str, cache_root: Path, bitrate: str) -> Path:
    """Transcode ``source`` to a cached AAC (.m4a) file and return its path.

    Cached by ``track_id`` so repeat requests are cheap and the result supports range requests
    (seekable). Raises :class:`TranscodeUnavailable` if ffmpeg is missing or the encode fails.
    """
    cache_root.mkdir(parents=True, exist_ok=True)
    output = cache_root / f"{track_id}.m4a"
    if output.is_file() and output.stat().st_size > 0:
        return output

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise TranscodeUnavailable("ffmpeg is not installed.")

    temp = cache_root / f"{track_id}.{os.getpid()}.tmp.m4a"
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                bitrate,
                "-movflags",
                "+faststart",
                str(temp),
            ],
            check=True,
            timeout=600,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        temp.unlink(missing_ok=True)
        raise TranscodeUnavailable(f"ffmpeg failed: {exc}") from exc

    if not temp.is_file() or temp.stat().st_size == 0:
        temp.unlink(missing_ok=True)
        raise TranscodeUnavailable("ffmpeg produced no output.")
    temp.replace(output)
    return output
