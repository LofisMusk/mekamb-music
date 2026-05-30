from pathlib import Path

import pytest

from app.core.runtime import RuntimeConfigurationError, prepare_runtime, validate_sandbox_paths


class SettingsLike:
    def __init__(self, *, quarantine_root: Path, library_root: Path, storage_backend: str = "local"):
        self.quarantine_root = quarantine_root
        self.library_root = library_root
        self.storage_backend = storage_backend


def test_prepare_runtime_creates_library_and_quarantine_dirs(tmp_path: Path):
    quarantine = tmp_path / "quarantine"
    library = tmp_path / "library"

    prepare_runtime(SettingsLike(quarantine_root=quarantine, library_root=library))

    assert quarantine.is_dir()
    assert library.is_dir()


def test_validate_sandbox_paths_rejects_nested_roots(tmp_path: Path):
    with pytest.raises(RuntimeConfigurationError, match="LIBRARY_ROOT must not be inside"):
        validate_sandbox_paths(
            quarantine_root=tmp_path / "quarantine",
            library_root=tmp_path / "quarantine" / "library",
        )

    with pytest.raises(RuntimeConfigurationError, match="QUARANTINE_ROOT must not be inside"):
        validate_sandbox_paths(
            quarantine_root=tmp_path / "library" / "quarantine",
            library_root=tmp_path / "library",
        )


def test_prepare_runtime_rejects_unknown_storage_backend(tmp_path: Path):
    with pytest.raises(RuntimeConfigurationError, match="Unsupported STORAGE_BACKEND"):
        prepare_runtime(
            SettingsLike(
                quarantine_root=tmp_path / "quarantine",
                library_root=tmp_path / "library",
                storage_backend="ftp",
            )
        )

