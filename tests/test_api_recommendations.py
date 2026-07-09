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


def test_autoplay_endpoint_response_includes_discovery_reason_when_applicable():
    # NOTE: the API test harness uses a fake engine (seeding real audio-feature /
    # personalization data through the DB layer here is impractical), so we exercise the
    # sequencing-tagged reason at the schema boundary: the engine returns a track carrying
    # "discovery" (as Pillar 3's _sequence_autoplay_batch does), and we assert the endpoint
    # (1) still validates against the unchanged AutoplayQueueResponse schema and
    # (2) preserves the discovery tag + keeps reasons a list of strings (backward compat).
    from app.api.schemas import AutoplayQueueResponse

    seed = FakeTrack()
    cold = FakeTrack()
    warm = FakeTrack()

    class DiscoveryEngine(FakeAutoplayEngine):
        async def autoplay_queue(self, seed_track_id, *, exclude_track_ids, limit):
            if seed_track_id != self.seed.id:
                raise LookupError(f"Track {seed_track_id} not found.")
            return [
                LocalTrackRecommendation(
                    track=cold, score=10.0, reasons=["audio_similarity", "discovery"]
                ),
                LocalTrackRecommendation(track=warm, score=9.0, reasons=["artist_interest"]),
            ]

    engine = DiscoveryEngine(seed, [cold, warm])
    try:
        response = _client(engine).get(f"/recommendations/autoplay?seed_track_id={seed.id}&limit=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    # Backward compatibility: response still validates against the unchanged schema.
    validated = AutoplayQueueResponse.model_validate(payload)
    for item in validated.tracks:
        assert isinstance(item.reasons, list)
        assert all(isinstance(reason, str) for reason in item.reasons)
    assert any("discovery" in item.reasons for item in validated.tracks)


def test_autoplay_missing_seed_returns_404():
    engine = FakeAutoplayEngine(FakeTrack(), [])
    try:
        response = _client(engine).get(f"/recommendations/autoplay?seed_track_id={uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
