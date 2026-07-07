from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.api.routes.recommendations import _parse_uuid_list
from app.db.models import Track, TrackAudioFeature
from app.recommendations.engine import (
    LocalTrackRecommendation,
    PersonalizationProfile,
    RecommendationEngine,
    _diversify_recommendations,
    _score_track_against_seed,
)
from app.recommendations.gemini import GeminiRateLimited


class RateLimitedGemini:
    @property
    def is_configured(self) -> bool:
        return True

    async def rerank(self, **kwargs):
        raise GeminiRateLimited("quota exhausted")


def test_audio_features_increase_local_similarity_score():
    seed = _track(title="Night Drive", artist="Mekamb", album="Late")
    similar = _track(title="Midnight Road", artist="Other", album="Else")
    different = _track(title="Morning Piano", artist="Other", album="Else")

    seed_feature = _feature(seed, tempo=122, energy=0.09, mfcc=[10.0] * 13)
    similar_feature = _feature(similar, tempo=124, energy=0.10, mfcc=[10.5] * 13)
    different_feature = _feature(different, tempo=70, energy=0.02, mfcc=[-4.0] * 13)

    similar_score = _score_track_against_seed(
        seed,
        similar,
        seed_feature=seed_feature,
        candidate_feature=similar_feature,
    )
    different_score = _score_track_against_seed(
        seed,
        different,
        seed_feature=seed_feature,
        candidate_feature=different_feature,
    )

    assert similar_score.score > different_score.score
    assert "audio_similarity" in similar_score.reasons
    assert "similar_tempo" in similar_score.reasons


@pytest.mark.asyncio
async def test_gemini_rate_limit_falls_back_to_python_ranking():
    seed = _track(title="Seed", artist="A", album="One")
    first = LocalTrackRecommendation(
        track=_track(title="First", artist="A", album="One"),
        score=20,
        reasons=["same_artist"],
    )
    second = LocalTrackRecommendation(
        track=_track(title="Second", artist="B", album="Two"),
        score=10,
        reasons=["metadata_overlap"],
    )
    engine = RecommendationEngine(
        session=None,
        piratebay=None,
        personal_1337x=None,
        indexer=None,
        gemini_client=RateLimitedGemini(),
    )

    ranked = await engine._maybe_gemini_rerank(seed, [first, second], limit=2)

    assert ranked == [first, second]


class AutoplayFakeSession:
    """Applies the statement's UUID bind params as an exclusion set, mimicking the
    real query's Track.id.not_in(...) clause."""

    def __init__(self, seed: Track, candidates: list[Track]):
        self.seed = seed
        self.candidates = candidates

    async def get(self, model, track_id):
        return self.seed if track_id == self.seed.id else None

    async def scalars(self, stmt):
        from uuid import UUID

        params = stmt.compile().params
        excluded = {value for value in params.values() if isinstance(value, UUID)}
        return [track for track in self.candidates if track.id not in excluded]


def _autoplay_engine(seed: Track, candidates: list[Track], *, recently_played: set) -> RecommendationEngine:
    engine = RecommendationEngine(
        session=AutoplayFakeSession(seed, candidates),
        piratebay=None,
        personal_1337x=None,
        indexer=None,
    )

    async def fake_recent():
        return recently_played

    async def fake_features(track_ids):
        return {}

    async def fake_profile():
        return PersonalizationProfile(
            track_weights={},
            artist_weights={},
            album_weights={},
            token_weights={},
            seed_labels=[],
        )

    engine._recently_played_track_ids = fake_recent
    engine._features_by_track_ids = fake_features
    engine._personalization_profile = fake_profile
    return engine


@pytest.mark.asyncio
async def test_autoplay_queue_excludes_queue_and_recent_plays_and_caps_artist():
    seed = _track(title="Seed", artist="A", album="One")
    same_artist = [_track(title=f"A{i}", artist="A", album="One") for i in range(5)]
    other = [_track(title=f"B{i}", artist="B", album="Two") for i in range(2)]
    queued = _track(title="Queued", artist="C", album="Three")
    just_played = _track(title="Just played", artist="D", album="Four")

    engine = _autoplay_engine(
        seed,
        [*same_artist, *other, queued, just_played],
        recently_played={just_played.id},
    )
    result = await engine.autoplay_queue(seed.id, exclude_track_ids={queued.id}, limit=5)

    result_ids = {item.track.id for item in result}
    assert seed.id not in result_ids
    assert queued.id not in result_ids
    assert just_played.id not in result_ids
    assert len(result) == 5
    assert result[0].track.artist == "A"
    assert sum(1 for item in result if item.track.artist == "A") == 3
    assert sum(1 for item in result if item.track.artist == "B") == 2


@pytest.mark.asyncio
async def test_autoplay_queue_missing_seed_raises():
    seed = _track(title="Seed", artist="A", album="One")
    engine = _autoplay_engine(seed, [], recently_played=set())

    with pytest.raises(LookupError):
        await engine.autoplay_queue(uuid4(), exclude_track_ids=set(), limit=5)


def test_diversify_recommendations_caps_per_artist_then_backfills():
    items = [
        LocalTrackRecommendation(track=_track(title=f"A{i}", artist="A", album="One"), score=100 - i, reasons=[])
        for i in range(5)
    ]
    capped = _diversify_recommendations(items, limit=3, max_per_artist=2)
    assert len(capped) == 3
    assert [item.track.title for item in capped] == ["A0", "A1", "A2"]


def test_parse_uuid_list_drops_malformed_entries():
    valid = uuid4()
    assert _parse_uuid_list(None) == set()
    assert _parse_uuid_list("") == set()
    assert _parse_uuid_list(f"{valid}, not-a-uuid ,") == {valid}


def _track(*, title: str, artist: str, album: str) -> Track:
    now = datetime.now(UTC)
    return Track(
        id=uuid4(),
        title=title,
        artist=artist,
        album=album,
        storage_key=f"{uuid4()}.mp3",
        original_filename=f"{title}.mp3",
        media_type="audio/mpeg",
        codec="mp3",
        duration_seconds=180,
        size_bytes=1234,
        created_at=now,
        last_accessed=now,
    )


def _feature(track: Track, *, tempo: float, energy: float, mfcc: list[float]) -> TrackAudioFeature:
    return TrackAudioFeature(
        track_id=track.id,
        tempo=tempo,
        energy=energy,
        chroma=0.45,
        spectral_centroid=2_200,
        mfcc=mfcc,
        mood_tags=[],
    )
