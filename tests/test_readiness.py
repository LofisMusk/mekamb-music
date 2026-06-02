from pathlib import Path

import pytest

from app.core.readiness import collect_readiness


class SettingsLike:
    def __init__(
        self,
        *,
        api_token: str,
        quarantine_root: Path,
        library_root: Path,
        storage_backend: str = "local",
    ):
        self.api_token = api_token
        self.quarantine_root = quarantine_root
        self.library_root = library_root
        self.storage_backend = storage_backend


async def ok_database_check() -> None:
    return None


async def failing_database_check() -> None:
    raise RuntimeError("database unavailable")


@pytest.mark.asyncio
async def test_collect_readiness_returns_ready_when_all_checks_pass(tmp_path: Path):
    quarantine = tmp_path / "quarantine"
    library = tmp_path / "library"
    quarantine.mkdir()
    library.mkdir()

    payload = await collect_readiness(
        SettingsLike(
            api_token="secret",
            quarantine_root=quarantine,
            library_root=library,
        ),
        database_check=ok_database_check,
    )

    assert payload["status"] == "ready"
    assert {check["status"] for check in payload["checks"]} == {"ok"}


@pytest.mark.asyncio
async def test_collect_readiness_reports_configuration_and_database_errors(tmp_path: Path):
    quarantine = tmp_path / "quarantine"
    library = tmp_path / "library"

    payload = await collect_readiness(
        SettingsLike(
            api_token="",
            quarantine_root=quarantine,
            library_root=library,
            storage_backend="ftp",
        ),
        database_check=failing_database_check,
    )

    assert payload["status"] == "not_ready"
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["api_token"]["status"] == "error"
    assert checks["storage_backend"]["status"] == "error"
    assert checks["quarantine_root"]["status"] == "error"
    assert checks["library_root"]["status"] == "error"
    assert checks["database"]["detail"] == "database unavailable"
