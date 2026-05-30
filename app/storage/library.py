from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


class ObjectStorage(Protocol):
    def put_file(self, source: Path, key: str):
        ...


class LibraryStorage:
    """Writes a streamable local cache and optionally mirrors objects remotely."""

    def __init__(self, *, local_cache: LocalStorage, remote: ObjectStorage | None = None) -> None:
        self.local_cache = local_cache
        self.remote = remote

    def put_file(self, source: Path, key: str) -> Path:
        cached_path = self.local_cache.put_file(source, key)
        if self.remote is not None:
            self.remote.put_file(source, key)
        return cached_path


def build_library_storage(settings: object) -> LibraryStorage:
    backend = getattr(settings, "storage_backend", "local").lower()
    local_cache = LocalStorage(getattr(settings, "library_root"))

    if backend == "local":
        return LibraryStorage(local_cache=local_cache)
    if backend == "s3":
        return LibraryStorage(local_cache=local_cache, remote=S3Storage.from_settings(settings))
    raise ValueError(f"Unsupported STORAGE_BACKEND {backend!r}. Use 'local' or 's3'.")

