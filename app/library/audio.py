from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

ALLOWED_AUDIO_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".alac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
}


@dataclass(frozen=True)
class AudioMetadata:
    title: str
    artist: str | None
    album: str | None
    media_type: str
    codec: str | None
    duration_seconds: int | None
    size_bytes: int


def is_allowed_audio_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS


def scan_audio_file(path: Path) -> AudioMetadata:
    if not is_allowed_audio_file(path):
        raise ValueError(f"Unsupported audio file: {path.name}")

    tags = None
    duration_seconds = None
    codec = path.suffix.lower().lstrip(".") or None
    try:
        from mutagen import File

        tags = File(path, easy=True)
        if tags and tags.info and getattr(tags.info, "length", None):
            duration_seconds = int(tags.info.length)
    except Exception:
        tags = None

    title = path.stem
    artist = None
    album = None
    if tags:
        title = _first_tag(tags, "title") or title
        artist = _first_tag(tags, "artist")
        album = _first_tag(tags, "album")

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return AudioMetadata(
        title=title,
        artist=artist,
        album=album,
        media_type=media_type,
        codec=codec,
        duration_seconds=duration_seconds,
        size_bytes=path.stat().st_size,
    )


def _first_tag(tags: object, key: str) -> str | None:
    try:
        values = tags.get(key)
    except Exception:
        return None
    if not values:
        return None
    return str(values[0])

