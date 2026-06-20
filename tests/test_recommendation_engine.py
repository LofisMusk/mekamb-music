from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.db.models import Track, TrackAudioFeature
from app.recommendations.engine import (
    LocalTrackRecommendation,
    RecommendationEngine,
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
