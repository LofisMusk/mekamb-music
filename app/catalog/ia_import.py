"""Pure matching/mapping helpers for the Internet Archive direct-push backfill.

The backfill worker (app/workers/ia_backfill_worker.py) does all the I/O; this
module holds the decision logic that's worth testing in isolation:

  * scoring an archive.org search hit against the (artist, album) we want, so we
    pick the *right* item out of archive.org's noisy global search (a title
    query for "Marmur" also returns court cases and 3D-print swatches), and
  * building the Lidarr Manual Import payload once files are downloaded and
    mapped to tracks.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# archive.org titles and identifiers are wildly inconsistent for the same album
# ("Taco Hemingway – Marmur (MP3)", "Taco-Hemingway-Marmur", "tacohem-marmur-2016"),
# so we match on a normalized token *set* rather than any kind of string equality.
_BRACKETED = re.compile(r"[(\[{].*?[)\]}]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# NFKD doesn't decompose these; map them by hand before the ascii fold.
_TRANSLIT = str.maketrans({"ł": "l", "Ł": "l", "ø": "o", "Ø": "o", "đ": "d", "Đ": "d"})
# Format/edition noise that shouldn't count toward (or against) a match.
_STOPWORDS = frozenset(
    {"mp3", "flac", "cd", "rip", "the", "a", "an", "ep", "lp", "album", "full", "official", "deluxe"}
)


def _tokenize(text: str) -> set[str]:
    # Fold to ASCII, but turn any dropped non-ASCII char into a *space* rather
    # than deleting it. Deleting glued tokens together across unusual separators
    # — e.g. "1‐800‐OŚWIECENIE" (U+2010 hyphens) collapsed into one token
    # "1800oswiecenie", which then never matched an item titled with normal
    # ASCII hyphens ("1-800-..."). Combining marks (accents) are still dropped so
    # "Ś"→"s".
    text = text.translate(_TRANSLIT)
    folded = []
    for ch in unicodedata.normalize("NFKD", text):
        if unicodedata.combining(ch):
            continue
        folded.append(ch if ch.isascii() else " ")
    text = "".join(folded).lower()
    text = _BRACKETED.sub(" ", text)
    return {tok for tok in _NON_ALNUM.split(text) if tok} - _STOPWORDS


def score_candidate(artist: str, album: str, *candidate_texts: str) -> float:
    """Score an archive.org hit in [0, 1] for how well it matches (artist, album).

    Requires most of the album's words to appear (a hard gate — otherwise a
    same-artist match on a *different* album would sneak through), then weights
    album match over artist match. Returns 0.0 for anything below the album
    gate so the caller can treat 0 as "not a match"."""
    album_tokens = _tokenize(album)
    if not album_tokens:
        return 0.0

    candidate_tokens: set[str] = set()
    for text in candidate_texts:
        candidate_tokens |= _tokenize(text)

    album_overlap = len(album_tokens & candidate_tokens) / len(album_tokens)
    if album_overlap < 0.5:
        return 0.0

    artist_tokens = _tokenize(artist)
    artist_overlap = (
        len(artist_tokens & candidate_tokens) / len(artist_tokens) if artist_tokens else 1.0
    )
    return round(0.7 * album_overlap + 0.3 * artist_overlap, 4)


@dataclass(frozen=True)
class IaCandidate:
    identifier: str
    title: str
    downloads: int
    score: float


def rank_candidates(artist: str, album: str, docs: list[dict[str, Any]]) -> list[IaCandidate]:
    """Score archive.org search docs and return the plausible ones, best first
    (highest score, then most-downloaded as a popularity tie-breaker that favors
    real releases over obscure re-uploads)."""
    ranked: list[IaCandidate] = []
    for doc in docs:
        identifier = str(doc.get("identifier") or "").strip()
        if not identifier:
            continue
        title = str(doc.get("title") or identifier).strip()
        score = score_candidate(artist, album, title, identifier)
        if score <= 0.0:
            continue
        ranked.append(IaCandidate(identifier, title, int(doc.get("downloads") or 0), score))
    ranked.sort(key=lambda c: (c.score, c.downloads), reverse=True)
    return ranked


# archive.org derives several formats per item; we pull one whole-album zip in a
# single format via its /compress/ endpoint. Prefer MP3 (smallest, universally
# accepted by Lidarr), fall back to lossless, then anything else audio. The
# strings must match archive.org's own `format` labels exactly.
_AUDIO_FORMAT_PREFERENCE = (
    "VBR MP3",
    "320Kbps MP3",
    "256Kbps MP3",
    "128Kbps MP3",
    "64Kbps MP3",
    "Flac",
    "24bit Flac",
    "Apple Lossless Audio",
    "AIFF",
    "WAVE",
    "Ogg Vorbis",
)


def select_audio_format(available_formats: list[str]) -> str | None:
    """Pick the best archive.org format label to bulk-download, or None if the
    item has no audio format we recognize."""
    present = {f.strip() for f in available_formats}
    for fmt in _AUDIO_FORMAT_PREFERENCE:
        if fmt in present:
            return fmt
    return None


def _has_permanent_rejection(candidate: dict[str, Any]) -> bool:
    for rejection in candidate.get("rejections") or []:
        # Lidarr marks blocking rejections "permanent"; warnings are advisory.
        if str(rejection.get("type", "permanent")).lower() == "permanent":
            return True
    return False


def build_manual_import_files(
    candidates: list[dict[str, Any]],
    *,
    artist_id: int,
    album_id: int,
) -> list[dict[str, Any]]:
    """Turn Lidarr's ``manualimport`` scan of our download folder into the
    payload for the ManualImport command.

    We scope the scan to the target ``albumId`` up front, so Lidarr's own matcher
    maps each file to the correct track (by tags/track-number) and reports the
    right ``albumReleaseId`` and parsed ``quality`` — all far more reliable than
    guessing. We just reshape its result, dropping any file it couldn't map to a
    track or that carries a blocking (permanent) rejection."""
    files: list[dict[str, Any]] = []
    for candidate in candidates:
        path = candidate.get("path")
        quality = candidate.get("quality")
        album_release_id = candidate.get("albumReleaseId")
        track_ids = [t["id"] for t in candidate.get("tracks") or [] if t.get("id")]
        if not path or quality is None or not album_release_id or not track_ids:
            continue
        if _has_permanent_rejection(candidate):
            continue
        files.append(
            {
                "path": path,
                "artistId": artist_id,
                "albumId": album_id,
                "albumReleaseId": album_release_id,
                "trackIds": track_ids,
                "quality": quality,
                "indexerFlags": 0,
                "disableReleaseSwitching": True,
            }
        )
    return files


_SANITIZE = re.compile(r'[/\\:*?"<>|\x00-\x1f]+')


def staging_folder_name(artist: str, album: str) -> str:
    """A filesystem-safe ``Artist - Album`` folder name for the download."""
    name = f"{artist.strip()} - {album.strip()}".strip(" -")
    return _SANITIZE.sub("_", name) or "ia-album"
