from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.deps import import_service, require_token
from app.core.auth import ApiKeyIdentity
from app.imports.domain import ImportRecord
from app.main import app


def _record(import_id: UUID | None = None, *, status: str = "ready_to_import") -> ImportRecord:
    now = datetime.now(UTC)
    return ImportRecord(
        id=import_id or uuid4(),
        source="lidarr",
        torrent_id="lidarr:42",
        info_hash="lidarr:42",
        magnet_link="",
        uploader="lidarr",
        source_url="lidarr",
        status=status,
        quarantine_path="/data/quarantine/import-id",
        error_message=None,
        created_at=now,
        updated_at=now,
    )


class FakeImportService:
    async def list_imports(self, *, status: str | None = None, limit: int = 50, offset: int = 0):
        return [_record(status=status or "ready_to_import")]

    async def get_import(self, import_id: UUID):
        return _record(import_id)

    async def cancel_import(self, import_id: UUID, *, delete_files: bool = True):
        return _record(import_id, status="canceled")


def _client():
    app.dependency_overrides[require_token] = lambda: ApiKeyIdentity(id="test", token="secret")
    app.dependency_overrides[import_service] = lambda: FakeImportService()
    return TestClient(app)


def test_list_imports_endpoint_returns_page():
    try:
        response = _client().get("/imports?status=queued&limit=10&offset=5")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["limit"] == 10
    assert payload["offset"] == 5
    assert payload["items"][0]["source"] == "lidarr"


def test_get_import_endpoint_returns_record():
    import_id = uuid4()
    try:
        response = _client().get(f"/imports/{import_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == str(import_id)


def test_cancel_import_endpoint_marks_import_canceled():
    import_id = uuid4()
    try:
        response = _client().post(f"/imports/{import_id}/cancel?delete_files=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(import_id)
    assert payload["status"] == "canceled"


def test_torrent_import_endpoints_are_gone():
    try:
        response = _client().post("/imports/1337x/123")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
