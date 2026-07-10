from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.deps import library_service, require_token
from app.core.auth import ApiKeyIdentity
from app.db.models import UserLibrary, UserLibraryTrack
from app.libraries.domain import (
    LibraryDetail,
    LibraryNotFound,
    LibrarySummary,
    LibraryTrackItem,
)
from app.main import app


def _detail(library_id: UUID, name: str = "My Library", tracks=()) -> LibraryDetail:
    now = datetime.now(UTC)
    return LibraryDetail(id=library_id, name=name, tracks=list(tracks), created_at=now, updated_at=now)


class FakeLibraryService:
    def __init__(self):
        self.created = None
        self.removed = None

    async def list_libraries(self, *, limit, offset):
        now = datetime.now(UTC)
        return [LibrarySummary(id=uuid4(), name="My Library", track_count=3, created_at=now, updated_at=now)]

    async def create_library(self, *, name):
        self.created = name
        return _detail(uuid4(), name=name)

    async def get_library(self, library_id):
        if library_id == UUID(int=0):
            raise LibraryNotFound("nope")
        return _detail(library_id)

    async def add_track(self, *, library_id, track_id):
        now = datetime.now(UTC)
        track = {
            "id": str(track_id),
            "title": "t",
            "artist": None,
            "album": None,
            "storage_key": "k/1",
            "original_filename": "1.flac",
            "media_type": "audio/flac",
            "codec": "flac",
            "duration_seconds": 1.0,
            "size_bytes": 10,
            "cover_key": None,
            "source_import_id": None,
            "created_at": now.isoformat(),
            "last_accessed": now.isoformat(),
        }
        item = LibraryTrackItem(position=1, added_at=now, track=track)
        return _detail(library_id, tracks=[item])

    async def remove_track(self, *, library_id, track_id):
        self.removed = (library_id, track_id)
        return _detail(library_id)


def _client(service):
    app.dependency_overrides[require_token] = lambda: ApiKeyIdentity(id="u1", token="t")
    app.dependency_overrides[library_service] = lambda: service
    return TestClient(app)


def test_create_and_list_libraries():
    service = FakeLibraryService()
    try:
        client = _client(service)
        created = client.post("/libraries", json={"name": "Chill"})
        listed = client.get("/libraries?limit=10&offset=0")
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 201
    assert created.json()["name"] == "Chill"
    assert service.created == "Chill"
    assert listed.status_code == 200
    assert listed.json()["items"][0]["track_count"] == 3


def test_add_track_returns_updated_library():
    service = FakeLibraryService()
    library_id = uuid4()
    track_id = uuid4()
    try:
        response = _client(service).post(f"/libraries/{library_id}/tracks", json={"track_id": str(track_id)})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["tracks"][0]["track"]["id"] == str(track_id)


def test_get_missing_library_returns_404():
    service = FakeLibraryService()
    try:
        response = _client(service).get(f"/libraries/{UUID(int=0)}")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_blank_library_name_is_rejected():
    service = FakeLibraryService()
    try:
        response = _client(service).post("/libraries", json={"name": "   "})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_models_are_scoped_and_unique():
    assert "api_key_id" in UserLibrary.__table__.columns
    constraint_names = {c.name for c in UserLibraryTrack.__table__.constraints if c.name}
    assert "uq_user_library_tracks_track" in constraint_names
