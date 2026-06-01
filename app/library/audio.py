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

MEDIA_TYPES_BY_EXTENSION = {
    ".aac": "audio/aac",
    ".aiff": "audio/aiff",
    ".alac": "audio/mp4",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
}

_COVER_FILENAMES = [
    "cover.jpg", "cover.jpeg", "cover.png",
    "folder.jpg", "folder.png",
    "front.jpg", "front.png",
    "artwork.jpg", "artwork.png",
    "albumart.jpg", "albumart.png",
]


@dataclass(frozen=True)
class AudioMetadata:
    title: str
    artist: str | None
    album: str | None
    media_type: str
    codec: str | None
    duration_seconds: float | None  # float — pliki < 1s nie zaokrąglają do 0
    size_bytes: int


@dataclass(frozen=True)
class EmbeddedArtwork:
    data: bytes
    media_type: str


def is_allowed_audio_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS


def scan_audio_file(path: Path) -> AudioMetadata:
    if not is_allowed_audio_file(path):
        raise ValueError(f"Unsupported audio file: {path.name}")

    tags = None
    duration_seconds: float | None = None
    codec = path.suffix.lower().lstrip(".") or None
    try:
        from mutagen import File

        tags = File(path, easy=True)
        if tags and tags.info and getattr(tags.info, "length", None):
            duration_seconds = float(tags.info.length)
    except Exception:
        tags = None

    title = path.stem
    artist = None
    album = None
    if tags:
        title = _first_tag(tags, "title") or title
        artist = _first_tag(tags, "artist")
        album = _first_tag(tags, "album")

    media_type = media_type_for_audio_file(path)
    return AudioMetadata(
        title=title,
        artist=artist,
        album=album,
        media_type=media_type,
        codec=codec,
        duration_seconds=duration_seconds,
        size_bytes=path.stat().st_size,
    )


def media_type_for_audio_file(path: Path) -> str:
    return (
        MEDIA_TYPES_BY_EXTENSION.get(path.suffix.lower())
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )


def extract_cover(audio_path: Path) -> tuple[bytes, str] | None:
    """
    Wyciągnij okładkę z pliku audio lub pliku graficznego w tym samym folderze.
    Zwraca (raw_bytes, mime_type) albo None.
    Próbuje najpierw pliku graficznego, potem embedded tag.
    """
    # 1. Plik graficzny w folderze
    for name in _COVER_FILENAMES:
        candidate = audio_path.parent / name
        if candidate.is_file():
            mime = "image/png" if candidate.suffix.lower() == ".png" else "image/jpeg"
            return candidate.read_bytes(), mime

    # 2. Embedded artwork przez istniejącą logikę
    artwork = extract_embedded_artwork(audio_path)
    if artwork:
        return artwork.data, artwork.media_type

    return None


def extract_embedded_artwork(path: Path) -> EmbeddedArtwork | None:
    if not is_allowed_audio_file(path):
        raise ValueError(f"Unsupported audio file: {path.name}")

    try:
        from mutagen import File

        audio = File(path)
    except Exception:
        return _extract_mp3_id3_file_artwork(path)

    if audio is None:
        return _extract_mp3_id3_file_artwork(path)

    artwork = _extract_picture_list_artwork(audio)
    if artwork is not None:
        return artwork

    tags = getattr(audio, "tags", None)
    if not tags:
        return None

    return (
        _extract_id3_artwork(tags)
        or _extract_mp4_artwork(tags)
        or _extract_vorbis_artwork(tags)
        or _extract_mp3_id3_file_artwork(path)
    )


def _first_tag(tags: object, key: str) -> str | None:
    try:
        values = tags.get(key)
    except Exception:
        return None
    if not values:
        return None
    return str(values[0])


def _extract_picture_list_artwork(audio: object) -> EmbeddedArtwork | None:
    for picture in getattr(audio, "pictures", []) or []:
        data = getattr(picture, "data", None)
        if data:
            media_type = getattr(picture, "mime", None) or "image/jpeg"
            return EmbeddedArtwork(data=bytes(data), media_type=media_type)
    return None


def _extract_id3_artwork(tags: object) -> EmbeddedArtwork | None:
    frames = []
    if hasattr(tags, "getall"):
        try:
            frames = list(tags.getall("APIC"))
        except Exception:
            frames = []
    if not frames:
        try:
            frames = [frame for frame in tags.values() if frame.__class__.__name__ == "APIC"]
        except Exception:
            frames = []

    for frame in frames:
        data = getattr(frame, "data", None)
        if data:
            media_type = getattr(frame, "mime", None) or "image/jpeg"
            return EmbeddedArtwork(data=bytes(data), media_type=media_type)
    return None


def _extract_mp3_id3_file_artwork(path: Path) -> EmbeddedArtwork | None:
    if path.suffix.lower() != ".mp3":
        return None
    try:
        from mutagen.id3 import ID3

        tags = ID3(path)
    except Exception:
        return None
    return _extract_id3_artwork(tags)


def _extract_mp4_artwork(tags: object) -> EmbeddedArtwork | None:
    try:
        covers = tags.get("covr")
    except Exception:
        return None
    if not covers:
        return None

    cover = covers[0]
    media_type = "image/jpeg"
    try:
        from mutagen.mp4 import MP4Cover

        if getattr(cover, "imageformat", None) == MP4Cover.FORMAT_PNG:
            media_type = "image/png"
    except Exception:
        pass
    return EmbeddedArtwork(data=bytes(cover), media_type=media_type)


def _extract_vorbis_artwork(tags: object) -> EmbeddedArtwork | None:
    try:
        encoded_pictures = tags.get("metadata_block_picture") or []
    except Exception:
        encoded_pictures = []

    for encoded in encoded_pictures:
        try:
            import base64

            from mutagen.flac import Picture

            picture = Picture(base64.b64decode(encoded))
        except Exception:
            continue
        if picture.data:
            return EmbeddedArtwork(
                data=bytes(picture.data),
                media_type=picture.mime or "image/jpeg",
            )

    try:
        cover_art = tags.get("coverart")
        cover_art_mime = tags.get("coverartmime")
    except Exception:
        return None
    if cover_art:
        try:
            import base64

            data = base64.b64decode(cover_art[0])
        except Exception:
            return None
        media_type = cover_art_mime[0] if cover_art_mime else "image/jpeg"
        return EmbeddedArtwork(data=data, media_type=media_type)
    return None
