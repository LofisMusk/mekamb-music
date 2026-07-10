from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.api.routes.recommendations import _parse_uuid_list
from app.db.models import Track, TrackAudioFeature, TrackNeighbor
from app.core.config import settings
from app.recommendations.engine import (
    LocalTrackRecommendation,
    PersonalizationProfile,
    RecommendationEngine,
    _arc_order,
    _diversify_recommendations,
    _score_track_against_seed,
    _sequence_autoplay_batch,
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


def test_score_track_against_seed_adds_collaborative_signal_reason():
    seed = _track(title="Seed", artist="A", album="One")
    candidate = _track(title="Cand", artist="B", album="Two")
    neighbor = TrackNeighbor(
        track_id=seed.id,
        neighbor_track_id=candidate.id,
        score=1.0,
        co_play_count=5,
    )

    without = _score_track_against_seed(seed, candidate)
    with_neighbor = _score_track_against_seed(
        seed, candidate, collaborative_neighbor=neighbor
    )

    assert "collaborative_signal" not in without.reasons
    assert "collaborative_signal" in with_neighbor.reasons
    assert with_neighbor.score > without.score


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


def _autoplay_engine(
    seed: Track,
    candidates: list[Track],
    *,
    recently_played: set,
    neighbors: dict | None = None,
) -> RecommendationEngine:
    engine = RecommendationEngine(
        session=AutoplayFakeSession(seed, candidates),
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

    async def fake_neighbors(seed_id, candidate_ids):
        return neighbors or {}

    engine._recently_played_track_ids = fake_recent
    engine._features_by_track_ids = fake_features
    engine._personalization_profile = fake_profile
    engine._collaborative_neighbors = fake_neighbors
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
async def test_autoplay_queue_includes_collaborative_neighbors_in_ranking():
    seed = _track(title="Seed", artist="A", album="One")
    # Two equal-metadata competitors (same artist/album/duration), so the only
    # differentiator is the collaborative neighbor signal on ``boosted``.
    boosted = _track(title="Boosted", artist="B", album="Two")
    plain = _track(title="Plain", artist="B", album="Two")

    neighbor = TrackNeighbor(
        track_id=seed.id,
        neighbor_track_id=boosted.id,
        score=1.5,
        co_play_count=7,
    )

    engine = _autoplay_engine(
        seed,
        [plain, boosted],
        recently_played=set(),
        neighbors={boosted.id: neighbor},
    )
    result = await engine.autoplay_queue(seed.id, exclude_track_ids=set(), limit=2)

    titles = [item.track.title for item in result]
    assert titles.index("Boosted") < titles.index("Plain")
    boosted_item = next(item for item in result if item.track.title == "Boosted")
    assert "collaborative_signal" in boosted_item.reasons


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


def _empty_profile(track_weights=None) -> PersonalizationProfile:
    return PersonalizationProfile(
        track_weights=track_weights or {},
        artist_weights={},
        album_weights={},
        token_weights={},
        seed_labels=[],
    )


def _rec(track: Track, *, score: float, reasons=None) -> LocalTrackRecommendation:
    return LocalTrackRecommendation(track=track, score=score, reasons=list(reasons or []))


def test_sequence_autoplay_batch_reserves_discovery_slots():
    limit = 10
    # 6 cold tracks (content-only reason, no history) and 4 personalized tracks.
    cold = [_track(title=f"Cold{i}", artist=f"C{i}", album="Cold") for i in range(6)]
    warm = [_track(title=f"Warm{i}", artist=f"W{i}", album="Warm") for i in range(4)]

    ranked = [_rec(t, score=100 - i, reasons=["audio_similarity"]) for i, t in enumerate(cold)]
    ranked += [
        _rec(t, score=90 - i, reasons=["artist_interest"]) for i, t in enumerate(warm)
    ]

    # Give the warm tracks personalization history too.
    profile = _empty_profile(track_weights={t.id: 5.0 for t in warm})

    result = _sequence_autoplay_batch(
        ranked,
        limit=limit,
        features_by_track_id={},
        profile=profile,
    )

    discovery_items = [item for item in result if "discovery" in item.reasons]
    expected = round(limit * settings.recommendation_discovery_slot_ratio)
    assert len(discovery_items) == expected
    warm_ids = {t.id for t in warm}
    for item in discovery_items:
        assert item.track.id not in warm_ids
        # None of the discovery-tagged items had a personalization reason beforehand.
        assert not any(
            r in {"artist_interest", "album_interest", "personal_signal", "collaborative_signal"}
            for r in item.reasons
            if r != "discovery"
        )


def test_sequence_autoplay_batch_preserves_first_track():
    # Distinct artists so the artist cap never drops the top track.
    tracks = [_track(title=f"T{i}", artist=f"A{i}", album="One") for i in range(6)]
    ranked = [_rec(t, score=100 - i, reasons=["audio_similarity"]) for i, t in enumerate(tracks)]

    result = _sequence_autoplay_batch(
        ranked,
        limit=6,
        features_by_track_id={},
        profile=_empty_profile(),
    )

    assert result[0].track.id == ranked[0].track.id


def test_arc_order_produces_rise_then_fall_energy_shape():
    tracks = [_track(title=f"T{i}", artist=f"A{i}", album="One") for i in range(7)]
    # Distinct descending energies fed in score order; arc should reshape positions 1..N-1.
    energies = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
    selected = [_rec(t, score=100 - i, reasons=[]) for i, t in enumerate(tracks)]
    features = {
        t.id: _feature(t, tempo=120, energy=e, mfcc=[1.0] * 13)
        for t, e in zip(tracks, energies, strict=True)
    }

    result = _arc_order(selected, features_by_track_id=features)

    tail_energies = [float(features[item.track.id].energy) for item in result[1:]]
    peak_index = tail_energies.index(max(tail_energies))
    middle_lo = len(tail_energies) // 4
    middle_hi = len(tail_energies) - 1 - len(tail_energies) // 4
    assert middle_lo <= peak_index <= middle_hi
    # And it is not a monotonic sequence (proves reordering happened).
    assert tail_energies != sorted(tail_energies, reverse=True)


def test_arc_order_keeps_no_feature_tracks_in_relative_order():
    tracks = [_track(title=f"T{i}", artist=f"A{i}", album="One") for i in range(6)]
    selected = [_rec(t, score=100 - i, reasons=[]) for i, t in enumerate(tracks)]
    # Only tracks at tail-index positions get features; leave some without.
    features = {
        tracks[1].id: _feature(tracks[1], tempo=120, energy=0.9, mfcc=[1.0] * 13),
        tracks[3].id: _feature(tracks[3], tempo=120, energy=0.5, mfcc=[1.0] * 13),
        tracks[5].id: _feature(tracks[5], tempo=120, energy=0.2, mfcc=[1.0] * 13),
    }
    no_data_ids_in_order = [tracks[2].id, tracks[4].id]

    result = _arc_order(selected, features_by_track_id=features)

    result_no_data = [item.track.id for item in result if item.track.id in no_data_ids_in_order]
    assert result_no_data == no_data_ids_in_order


def test_arc_order_short_list_unchanged():
    tracks = [_track(title=f"T{i}", artist=f"A{i}", album="One") for i in range(2)]
    selected = [_rec(t, score=100 - i, reasons=[]) for i, t in enumerate(tracks)]
    result = _arc_order(selected, features_by_track_id={})
    assert result == selected


@pytest.mark.asyncio
async def test_sequence_autoplay_batch_disabled_falls_back_to_diversify(monkeypatch):
    monkeypatch.setattr(settings, "recommendation_sequencing_enabled", False)
    seed = _track(title="Seed", artist="A", album="One")
    cold = [_track(title=f"Cold{i}", artist=f"C{i}", album="Cold") for i in range(4)]
    engine = _autoplay_engine(seed, cold, recently_played=set())

    result = await engine.autoplay_queue(seed.id, exclude_track_ids=set(), limit=4)

    assert all("discovery" not in item.reasons for item in result)


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
