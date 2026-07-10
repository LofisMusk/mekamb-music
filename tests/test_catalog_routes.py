from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import import_service, lidarr_client, require_token, require_user
from app.api.routes.catalog import _album_dir_from_payload, _foreign_key_from_payload
from app.core.auth import ApiKeyIdentity
from app.core.config import settings
from app.imports.domain import ImportRecord
from app.main import app


class FakeLidarr:
    def lookup(self, kind, term):
        if kind == "album":
            return [
                {
                    "foreignAlbumId": "album-1",
                    "title": "Geogaddi",
                    "artist": {"artistName": "Boards of Canada", "foreignArtistId": "artist-1"},
                    "releaseDate": "2002-02-18",
                }
            ]
        return [{"foreignArtistId": "artist-1", "artistName": "Boards of Canada"}]


class FakeImportService:
    def __init__(self):
        self.calls = []

    async def create_lidarr_import(self, *, source_dir, foreign_key, name, source_url="lidarr"):
        self.calls.append((str(source_dir), foreign_key, name))
        now = datetime.now(UTC)
        return ImportRecord(
            id=uuid4(),
            source="lidarr",
            torrent_id=foreign_key,
            info_hash=foreign_key,
            magnet_link="",
            uploader="lidarr",
            source_url=source_url,
            status="ready_to_import",
            quarantine_path="/data/quarantine/x",
            error_message=None,
            created_at=now,
            updated_at=now,
        )


class FakeSession:
    async def scalar(self, stmt):
        return None

    def add(self, item):
        self.item = item

    async def commit(self):
        return None


def _base_overrides():
    app.dependency_overrides[require_token] = lambda: ApiKeyIdentity(id="u1", token="t")
    app.dependency_overrides[require_user] = lambda: object()


def test_catalog_search_maps_artist_results():
    _base_overrides()
    app.dependency_overrides[lidarr_client] = lambda: FakeLidarr()
    try:
        response = TestClient(app).get("/catalog/search?q=boards&kind=artist")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "artist"
    assert payload["items"][0]["foreign_id"] == "artist-1"
    assert payload["items"][0]["title"] == "Boards of Canada"


def test_catalog_search_maps_album_results_with_artist_foreign_id():
    _base_overrides()
    app.dependency_overrides[lidarr_client] = lambda: FakeLidarr()
    try:
        response = TestClient(app).get("/catalog/search?q=geogaddi&kind=album")
    finally:
        app.dependency_overrides.clear()

    item = response.json()["items"][0]
    assert item["foreign_id"] == "album-1"
    assert item["artist_foreign_id"] == "artist-1"
    assert item["year"] == 2002


def test_webhook_rejects_bad_token(monkeypatch):
    monkeypatch.setattr(settings, "lidarr_webhook_token", "secret")
    fake = FakeImportService()
    app.dependency_overrides[import_service] = lambda: fake
    try:
        response = TestClient(app).post("/catalog/webhook?token=wrong", json={"eventType": "Download"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 401
    assert fake.calls == []


def test_webhook_test_event_is_ignored(monkeypatch):
    monkeypatch.setattr(settings, "lidarr_webhook_token", "")
    fake = FakeImportService()
    app.dependency_overrides[import_service] = lambda: fake
    try:
        response = TestClient(app).post("/catalog/webhook", json={"eventType": "Test"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert fake.calls == []


def test_webhook_import_event_queues_ingest(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "lidarr_webhook_token", "secret")
    album = tmp_path / "Artist" / "Album"
    album.mkdir(parents=True)
    (album / "01.flac").write_bytes(b"a")

    fake = FakeImportService()
    from app.api.deps import db_session

    app.dependency_overrides[import_service] = lambda: fake
    app.dependency_overrides[db_session] = lambda: FakeSession()
    payload = {
        "eventType": "Download",
        "album": {"foreignAlbumId": "album-1", "title": "Album"},
        "artist": {"artistName": "Artist"},
        "trackFiles": [{"path": str(album / "01.flac")}],
    }
    try:
        response = TestClient(app).post("/catalog/webhook?token=secret", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert fake.calls[0][0] == str(album)
    assert fake.calls[0][1] == "lidarr:album-1"


def test_payload_helpers():
    payload = {
        "album": {"foreignAlbumId": "abc"},
        "trackFiles": [{"path": "/music/Artist/Album/01.flac"}],
    }
    assert _album_dir_from_payload(payload) == "/music/Artist/Album"
    assert _foreign_key_from_payload(payload) == "lidarr:abc"
