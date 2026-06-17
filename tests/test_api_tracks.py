from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import db_session, require_token
from app.api.routes.tracks import (
    select_liked_track_for_track,
    select_liked_tracks,
    select_recent_playback_events,
    select_track_play_stats,
)
from app.core.auth import ApiKeyIdentity
from app.main import app


class FakeTrack:
    def __init__(self):
        self.id = uuid4()
        self.title = "Ambient One"
        self.artist = "Mekamb"
        self.album = "Private"
        self.storage_key = "ABC/track.mp3"
        self.original_filename = "track.mp3"
        self.media_type = "audio/mpeg"
        self.codec = "mp3"
        self.duration_seconds = 120
        self.size_bytes = 1234
        self.source_import_id = None
        self.created_at = datetime.now(UTC)
        self.last_accessed = self.created_at

    def to_dict(self):
        return {
            "id": str(self.id),
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "storage_key": self.storage_key,
            "original_filename": self.original_filename,
            "media_type": self.media_type,
            "codec": self.codec,
            "duration_seconds": self.duration_seconds,
            "size_bytes": self.size_bytes,
            "source_import_id": None,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
        }


class FakeSession:
    def __init__(self):
        self.statements = []

    async def scalars(self, statement):
        self.statements.append(statement)
        return [FakeTrack()]

    async def execute(self, statement):
        self.statements.append(statement)
        return [
            {
                "name": "Mekamb",
                "track_count": 2,
                "latest_track_at": datetime(2026, 5, 30, tzinfo=UTC),
            }
        ]


class FakeAlbumSession(FakeSession):
    async def execute(self, statement):
        self.statements.append(statement)
        return [
            {
                "title": "Private",
                "artist": "Mekamb",
                "track_count": 2,
                "latest_track_at": datetime(2026, 5, 30, tzinfo=UTC),
            }
        ]


def test_tracks_endpoint_returns_searchable_page():
    fake_session = FakeSession()
    app.dependency_overrides[require_token] = lambda: ApiKeyIdentity(id="test", token="secret")
    app.dependency_overrides[db_session] = lambda: fake_session
    try:
        response = TestClient(app).get("/tracks?q=ambient&limit=25&offset=50")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "ambient"
    assert payload["limit"] == 25
    assert payload["offset"] == 50
    assert payload["items"][0]["title"] == "Ambient One"
    compiled = str(fake_session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "ambient" in compiled
    assert "LIMIT 25" in compiled
    assert "OFFSET 50" in compiled


def test_artists_endpoint_returns_artist_page():
    fake_session = FakeSession()
    app.dependency_overrides[require_token] = lambda: ApiKeyIdentity(id="test", token="secret")
    app.dependency_overrides[db_session] = lambda: fake_session
    try:
        response = TestClient(app).get("/tracks/artists?q=mek&limit=20&offset=5")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "mek"
    assert payload["limit"] == 20
    assert payload["offset"] == 5
    assert payload["items"][0]["name"] == "Mekamb"
    assert payload["items"][0]["track_count"] == 2
    assert payload["items"][0]["latest_track_at"] == "2026-05-30T00:00:00Z"


def test_albums_endpoint_returns_album_page():
    fake_session = FakeAlbumSession()
    app.dependency_overrides[require_token] = lambda: ApiKeyIdentity(id="test", token="secret")
    app.dependency_overrides[db_session] = lambda: fake_session
    try:
        response = TestClient(app).get("/tracks/albums?q=private&limit=15&offset=0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "private"
    assert payload["items"][0]["title"] == "Private"
    assert payload["items"][0]["artist"] == "Mekamb"
    assert payload["items"][0]["track_count"] == 2


def test_personal_track_queries_are_scoped_to_api_key():
    track_id = uuid4()
    statements = [
        select_liked_tracks(api_key_id="alice", limit=25, offset=0),
        select_liked_track_for_track(track_id, api_key_id="alice"),
        select_track_play_stats(track_id, api_key_id="alice"),
        select_recent_playback_events(api_key_id="alice", limit=25, offset=0),
    ]

    for statement in statements:
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert "api_key_id" in compiled
        assert "alice" in compiled
