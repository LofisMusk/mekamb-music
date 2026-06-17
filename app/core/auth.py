from __future__ import annotations

import re
from dataclasses import dataclass
from secrets import compare_digest
from typing import Protocol


DEFAULT_API_KEY_ID = "default"


class AuthSettings(Protocol):
    api_token: str
    api_tokens: str


@dataclass(frozen=True)
class ApiKeyIdentity:
    id: str
    token: str


def configured_api_keys(settings: AuthSettings) -> list[ApiKeyIdentity]:
    keys: list[ApiKeyIdentity] = []
    seen_ids: set[str] = set()

    if settings.api_token:
        keys.append(ApiKeyIdentity(id=DEFAULT_API_KEY_ID, token=settings.api_token))
        seen_ids.add(DEFAULT_API_KEY_ID)

    for index, raw_entry in enumerate(settings.api_tokens.split(","), start=1):
        entry = raw_entry.strip()
        if not entry:
            continue
        key_id, token = _split_api_token_entry(entry, fallback_id=f"key_{index}")
        key_id = normalize_api_key_id(key_id)
        if not token or key_id in seen_ids:
            continue
        keys.append(ApiKeyIdentity(id=key_id, token=token))
        seen_ids.add(key_id)

    return keys


def match_bearer_token(settings: AuthSettings, authorization: str | None) -> ApiKeyIdentity | None:
    if not authorization:
        return None

    parts = authorization.strip().split(None, 1)
    if len(parts) != 2:
        return None

    scheme, token = parts
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return None

    for api_key in configured_api_keys(settings):
        if compare_digest(token, api_key.token.strip()):
            return api_key
    return None


def normalize_api_key_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-")
    return (normalized or DEFAULT_API_KEY_ID)[:64]


def _split_api_token_entry(entry: str, *, fallback_id: str) -> tuple[str, str]:
    for separator in ("=", ":"):
        if separator in entry:
            key_id, token = entry.split(separator, 1)
            return key_id.strip(), token.strip()
    return fallback_id, entry
