from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from app.core.runtime import (
    RuntimeConfigurationError,
    validate_sandbox_paths,
    validate_storage_backend,
)


async def collect_readiness(
    settings: object,
    *,
    database_check: Callable[[], Awaitable[None]],
    redis_check: Callable[[], Awaitable[None]] | None = None,
    lidarr_check: Callable[[], Awaitable[None]] | None = None,
) -> dict[str, object]:
    checks = [
        _check_api_token(settings),
        _check_storage_backend(settings),
        _check_sandbox_paths(settings),
        _check_directory("quarantine_root", getattr(settings, "quarantine_root")),
        _check_directory("library_root", getattr(settings, "library_root")),
        await _check_redis(redis_check),
        await _check_lidarr(lidarr_check),
        await _check_database(database_check),
    ]
    status = "ready" if all(check["status"] == "ok" for check in checks) else "not_ready"
    return {"status": status, "checks": checks}


def _check_api_token(settings: object) -> dict[str, str]:
    if getattr(settings, "api_token", "") or getattr(settings, "api_tokens", ""):
        return _ok("api_token")
    return _error("api_token", "API_TOKEN or API_TOKENS is not configured.")


def _check_storage_backend(settings: object) -> dict[str, str]:
    try:
        validate_storage_backend(getattr(settings, "storage_backend", "local"))
    except RuntimeConfigurationError as exc:
        return _error("storage_backend", str(exc))
    return _ok("storage_backend")


def _check_sandbox_paths(settings: object) -> dict[str, str]:
    try:
        validate_sandbox_paths(
            quarantine_root=Path(getattr(settings, "quarantine_root")).expanduser().resolve(),
            library_root=Path(getattr(settings, "library_root")).expanduser().resolve(),
        )
    except RuntimeConfigurationError as exc:
        return _error("sandbox_paths", str(exc))
    return _ok("sandbox_paths")


def _check_directory(name: str, path_value: object) -> dict[str, str]:
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        return _error(name, f"{path} does not exist.")
    if not path.is_dir():
        return _error(name, f"{path} is not a directory.")
    probe = path / ".mekamb-music-write-test"
    try:
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        return _error(name, f"{path} is not writable: {exc}.")
    return _ok(name)


async def _check_database(database_check: Callable[[], Awaitable[None]]) -> dict[str, str]:
    try:
        await database_check()
    except Exception as exc:
        return _error("database", str(exc))
    return _ok("database")


async def _check_redis(redis_check: Callable[[], Awaitable[None]] | None) -> dict[str, str]:
    if redis_check is None:
        return _ok("redis")
    try:
        await redis_check()
    except Exception as exc:
        return _error("redis", str(exc))
    return _ok("redis")


async def _check_lidarr(
    lidarr_check: Callable[[], Awaitable[None]] | None,
) -> dict[str, str]:
    if lidarr_check is None:
        return _ok("lidarr")
    try:
        await lidarr_check()
    except Exception as exc:
        return _error("lidarr", str(exc))
    return _ok("lidarr")


def _ok(name: str) -> dict[str, str]:
    return {"name": name, "status": "ok", "detail": "ok"}


def _error(name: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": "error", "detail": detail}
