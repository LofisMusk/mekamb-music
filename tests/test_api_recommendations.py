from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.deps import require_token
from app.api.routes.recommendations import _recommendation_engine
from app.core.auth import ApiKeyIdentity
from app.main import app
from app.recommendations.engine import LocalTrackRecommendation
from tests.test_api_tracks import FakeTrack


class FakeAutoplayEngine:
    def __init__(self, seed: FakeTrack, tracks: list[FakeTrack]):
        self.seed = seed
        self.tracks = tracks
        self.calls: list[dict[str, object]] = []
        self.session = self

    async def get(self, model, track_id):
        return self.seed if track_id == self.seed.id else None

    async def autoplay_queue(self, seed_track_id: UUID, *, exclude_track_ids: set[UUID], limit: int):
        self.calls.append(
            {"seed_track_id": seed_track_id, "exclude_track_ids": exclude_track_ids, "limit": limit}
        )
        if seed_track_id != self.seed.id:
            raise LookupError(f"Track {seed_track_id} not found.")
        return [
            LocalTrackRecommendation(track=track, score=10.0, reasons=["same_artist"])
            for track in self.tracks[:limit]
        ]


def _client(engine: FakeAutoplayEngine) -> TestClient:
    app.dependency_overrides[require_token] = lambda: ApiKeyIdentity(id="test", token="secret")
    app.dependency_overrides[_recommendation_engine] = lambda: engine
    return TestClient(app)


def test_autoplay_returns_continuation_and_forwards_params():
    seed = FakeTrack()
    recommended = [FakeTrack(), FakeTrack()]
    engine = FakeAutoplayEngine(seed, recommended)
    excluded = uuid4()
    try:
        response = _client(engine).get(
            f"/recommendations/autoplay?seed_track_id={seed.id}&exclude={excluded},garbage-id&limit=2"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["seed_track"]["id"] == str(seed.id)
    assert [item["track"]["id"] for item in payload["tracks"]] == [str(t.id) for t in recommended]
    assert payload["tracks"][0]["reasons"] == ["same_artist"]

    call = engine.calls[0]
    assert call["seed_track_id"] == seed.id
    assert call["exclude_track_ids"] == {excluded}  # malformed entries silently dropped
    assert call["limit"] == 2


def test_autoplay_missing_seed_returns_404():
    engine = FakeAutoplayEngine(FakeTrack(), [])
    try:
        response = _client(engine).get(f"/recommendations/autoplay?seed_track_id={uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
