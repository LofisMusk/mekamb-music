"""Data-scope identity primitives.

Authentication is exclusively session-token based (``app/auth/service.py``); the
legacy raw ``API_TOKEN(S)`` bearer scheme has been removed. What remains here is
the ``api_key_id`` data-scope concept every request resolves to: an account's
``api_key_id`` scopes its personal data (likes, plays, playlists, playback, sync,
libraries). ``DEFAULT_API_KEY_ID`` is still the column default for legacy rows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


DEFAULT_API_KEY_ID = "default"


@dataclass(frozen=True)
class ApiKeyIdentity:
    id: str
    token: str


def normalize_api_key_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-")
    return (normalized or DEFAULT_API_KEY_ID)[:64]
