from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.deps import download_service, require_token
from app.downloads.domain import DownloadStatus, TorrentRuntimeStatus
from app.imports.domain import ImportNotFound, ImportRecord
from app.main import app


class FakeDownloadService:
    async def get_download_status(self, import_id: UUID):
        now = datetime.now(UTC)
        return DownloadStatus(
            import_record=ImportRecord(
                id=import_id,
                source="personal_1337x",
                torrent_id="123",
                info_hash="ABC123",
                magnet_link="magnet:?xt=urn:btih:ABC123",
                uploader="mekamb",
                source_url="https://1337x.to/torrent/123/mine/",
                status="queued",
                quarantine_path="/data/quarantine/import-id",
                error_message=None,
                created_at=now,
                updated_at=now,
            ),
            torrent=TorrentRuntimeStatus(
                name="track.flac",
                info_hash="ABC123",
                state="downloading",
                progress=0.5,
                size_bytes=1000,
                downloaded_bytes=500,
                download_speed_bytes=25,
                eta_seconds=20,
                save_path="/downloads/incomplete/import-id",
            ),
        )


class MissingDownloadService:
    async def get_download_status(self, import_id: UUID):
        raise ImportNotFound(f"Import {import_id} not found.")


def _client(service):
    app.dependency_overrides[require_token] = lambda: None
    app.dependency_overrides[download_service] = lambda: service
    return TestClient(app)


def test_download_endpoint_returns_import_and_torrent_status():
    import_id = uuid4()
    try:
        response = _client(FakeDownloadService()).get(f"/downloads/{import_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["import"]["id"] == str(import_id)
    assert payload["import"]["status"] == "queued"
    assert payload["torrent"]["state"] == "downloading"
    assert payload["torrent"]["progress"] == 0.5


def test_download_endpoint_returns_404_for_missing_import():
    try:
        response = _client(MissingDownloadService()).get(f"/downloads/{uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404

