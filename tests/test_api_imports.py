from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.deps import db_session, import_service, personal_1337x_provider, require_token
from app.core.auth import ApiKeyIdentity
from app.imports.domain import ImportRecord
from app.main import app
from app.sources.personal_1337x import (
    MissingTorrentMetadata,
    Personal1337xImportCandidate,
)


class SuccessProvider:
    async def resolve_for_import(self, torrent_id: str):
        return Personal1337xImportCandidate(
            torrent_id=torrent_id,
            info_hash="ABC123",
            magnet_link="magnet:?xt=urn:btih:ABC123",
            uploader="mekamb",
            source_url=f"https://1337x.to/torrent/{torrent_id}/mine/",
            name="mine",
            fetched_at=datetime.now(UTC),
        )


class MissingMetadataProvider:
    async def resolve_for_import(self, torrent_id: str):
        raise MissingTorrentMetadata("Torrent has no magnet link.")


class FakeImportService:
    async def list_imports(self, *, status: str | None = None, limit: int = 50, offset: int = 0):
        now = datetime.now(UTC)
        return [
            ImportRecord(
                id=uuid4(),
                source="personal_1337x",
                torrent_id="1",
                info_hash="ABC123",
                magnet_link="magnet:?xt=urn:btih:ABC123",
                uploader="mekamb",
                source_url="https://1337x.to/torrent/1/mine/",
                status=status or "queued",
                quarantine_path="/data/quarantine/import-id",
                error_message=None,
                created_at=now,
                updated_at=now,
            )
        ]

    async def create_1337x_import(self, candidate: Personal1337xImportCandidate):
        now = datetime.now(UTC)
        return ImportRecord(
            id=uuid4(),
            source="personal_1337x",
            torrent_id=candidate.torrent_id,
            info_hash=candidate.info_hash,
            magnet_link=candidate.magnet_link,
            uploader=candidate.uploader,
            source_url=candidate.source_url,
            status="queued",
            quarantine_path="/data/quarantine/import-id",
            error_message=None,
            created_at=now,
            updated_at=now,
        )

    async def get_import(self, import_id: UUID):
        now = datetime.now(UTC)
        return ImportRecord(
            id=import_id,
            source="personal_1337x",
            torrent_id="1",
            info_hash="ABC123",
            magnet_link="magnet:?xt=urn:btih:ABC123",
            uploader="mekamb",
            source_url="https://1337x.to/torrent/1/mine/",
            status="queued",
            quarantine_path="/data/quarantine/import-id",
            error_message=None,
            created_at=now,
            updated_at=now,
        )

    async def cancel_import(self, import_id: UUID, *, delete_files: bool = True):
        now = datetime.now(UTC)
        return ImportRecord(
            id=import_id,
            source="personal_1337x",
            torrent_id="1",
            info_hash="ABC123",
            magnet_link="magnet:?xt=urn:btih:ABC123",
            uploader="mekamb",
            source_url="https://1337x.to/torrent/1/mine/",
            status="canceled",
            quarantine_path="/data/quarantine/import-id",
            error_message=None,
            created_at=now,
            updated_at=now,
        )


class FakeSession:
    def add(self, item):
        self.item = item

    async def commit(self):
        return None

    async def refresh(self, item):
        return None


def _client(provider):
    app.dependency_overrides[require_token] = lambda: ApiKeyIdentity(id="test", token="secret")
    app.dependency_overrides[personal_1337x_provider] = lambda: provider
    app.dependency_overrides[import_service] = lambda: FakeImportService()
    app.dependency_overrides[db_session] = lambda: FakeSession()
    return TestClient(app)


def test_import_endpoint_queues_verified_personal_torrent():
    try:
        response = _client(SuccessProvider()).post("/imports/1337x/123")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    payload = response.json()
    assert payload["source"] == "personal_1337x"
    assert payload["torrent_id"] == "123"
    assert payload["uploader"] == "mekamb"
    assert payload["status"] == "queued"


def test_import_endpoint_rejects_missing_torrent_metadata():
    try:
        response = _client(MissingMetadataProvider()).post("/imports/1337x/123")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "magnet link" in response.json()["detail"]


def test_list_imports_endpoint_returns_page():
    try:
        response = _client(SuccessProvider()).get("/imports?status=queued&limit=10&offset=5")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["limit"] == 10
    assert payload["offset"] == 5
    assert payload["items"][0]["status"] == "queued"


def test_cancel_import_endpoint_marks_import_canceled():
    import_id = uuid4()
    try:
        response = _client(SuccessProvider()).post(f"/imports/{import_id}/cancel?delete_files=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(import_id)
    assert payload["status"] == "canceled"
