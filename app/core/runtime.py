from pathlib import Path


class RuntimeConfigurationError(RuntimeError):
    pass


def prepare_runtime(settings: object) -> None:
    validate_storage_backend(getattr(settings, "storage_backend", "local"))
    quarantine_root = _resolve_path(getattr(settings, "quarantine_root"))
    library_root = _resolve_path(getattr(settings, "library_root"))
    validate_sandbox_paths(quarantine_root=quarantine_root, library_root=library_root)
    quarantine_root.mkdir(parents=True, exist_ok=True)
    library_root.mkdir(parents=True, exist_ok=True)


def validate_storage_backend(storage_backend: str) -> None:
    if storage_backend.lower() not in {"local", "s3"}:
        raise RuntimeConfigurationError(
            f"Unsupported STORAGE_BACKEND {storage_backend!r}. Use 'local' or 's3'."
        )


def validate_sandbox_paths(*, quarantine_root: Path, library_root: Path) -> None:
    if quarantine_root == library_root:
        raise RuntimeConfigurationError("QUARANTINE_ROOT and LIBRARY_ROOT must be different paths.")
    if library_root in quarantine_root.parents:
        raise RuntimeConfigurationError("QUARANTINE_ROOT must not be inside LIBRARY_ROOT.")
    if quarantine_root in library_root.parents:
        raise RuntimeConfigurationError("LIBRARY_ROOT must not be inside QUARANTINE_ROOT.")


def _resolve_path(value: object) -> Path:
    return Path(value).expanduser().resolve()

