from pathlib import Path

import pytest

from app.storage.library import LibraryStorage, build_library_storage
from app.storage.local import LocalStorage


class FakeRemoteStorage:
    def __init__(self):
        self.uploads = []

    def put_file(self, source: Path, key: str):
        self.uploads.append((source.read_bytes(), key))
        return key


class SettingsLike:
    def __init__(self, *, library_root: Path, storage_backend: str):
        self.library_root = library_root
        self.storage_backend = storage_backend


def test_library_storage_keeps_local_cache_and_mirrors_remote(tmp_path: Path):
    source = tmp_path / "track.flac"
    source.write_bytes(b"lossless audio bytes")
    remote = FakeRemoteStorage()
    storage = LibraryStorage(local_cache=LocalStorage(tmp_path / "library"), remote=remote)

    cached_path = storage.put_file(source, "abc/track.flac")

    assert cached_path.read_bytes() == b"lossless audio bytes"
    assert remote.uploads == [(b"lossless audio bytes", "abc/track.flac")]


def test_build_library_storage_rejects_unknown_backend(tmp_path: Path):
    with pytest.raises(ValueError, match="Unsupported STORAGE_BACKEND"):
        build_library_storage(SettingsLike(library_root=tmp_path / "library", storage_backend="ftp"))

