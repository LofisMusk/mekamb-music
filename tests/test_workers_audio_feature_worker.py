from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.config import settings
from app.db.models import Track, TrackAudioFeature
from app.recommendations.audio_features import ExtractedAudioFeatures
from app.workers import audio_feature_worker


def _extracted() -> ExtractedAudioFeatures:
    return ExtractedAudioFeatures(
        tempo=120.0,
        energy=0.09,
        chroma=0.45,
        spectral_centroid=2200.0,
        mfcc=[10.0] * 13,
        mood_tags=["midtempo"],
        chroma_vector=[0.3] * 12,
        mfcc_delta=[0.5] * 13,
        spectral_contrast=[12.0] * 7,
        spectral_rolloff=3200.0,
        spectral_bandwidth=1800.0,
        zero_crossing_rate=0.08,
        harmonic_percussive_ratio=1.4,
    )


def _track(*, created_offset_seconds: int = 0, storage_key: str | None = None) -> Track:
    now = datetime.now(UTC) - timedelta(seconds=created_offset_seconds)
    return Track(
        id=uuid4(),
        title="Track",
        artist="Artist",
        album="Album",
        storage_key=storage_key or f"{uuid4()}.mp3",
        original_filename="track.mp3",
        media_type="audio/mpeg",
        codec="mp3",
        duration_seconds=180,
        size_bytes=1234,
        created_at=now,
        last_accessed=now,
    )


class FakeFeatureSession:
    """Mimics the worker's backlog outerjoin query and per-track get-or-create,
    matching the fake-session convention already used in the engine tests."""

    def __init__(self, tracks: list[Track], features: dict[UUID, TrackAudioFeature]):
        self.tracks = tracks
        self.features = features
        self.added: list[TrackAudioFeature] = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _needs_processing(self, track: Track) -> bool:
        feature = self.features.get(track.id)
        return feature is None or feature.features_version != settings.audio_feature_current_version

    async def scalars(self, stmt):
        # Backlog query: Track rows needing processing, oldest first, limited.
        params = stmt.compile().params
        limit = next((v for v in params.values() if isinstance(v, int)), None)
        ordered = sorted(self.tracks, key=lambda t: t.created_at)
        needing = [track for track in ordered if self._needs_processing(track)]
        if limit is not None:
            needing = needing[:limit]
        return needing

    async def scalar(self, stmt):
        # Per-track get-or-create: select TrackAudioFeature where track_id == :id
        params = stmt.compile().params
        track_id = next((v for v in params.values() if isinstance(v, UUID)), None)
        return self.features.get(track_id)

    def add(self, item):
        self.added.append(item)
        if isinstance(item, TrackAudioFeature):
            self.features[item.track_id] = item

    async def commit(self):
        self.commits += 1


class FakeStorage:
    def ensure_cached(self, storage_key: str) -> Path:
        return Path(f"/library/{storage_key}")


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch):
    def _apply(session: FakeFeatureSession, *, extractor=None):
        monkeypatch.setattr(audio_feature_worker, "AsyncSessionLocal", lambda: session)
        monkeypatch.setattr(audio_feature_worker, "build_library_storage", lambda _settings: FakeStorage())
        monkeypatch.setattr(
            audio_feature_worker,
            "extract_audio_features",
            extractor or (lambda path: _extracted()),
        )
        return session

    return _apply


@pytest.mark.asyncio
async def test_processes_missing_and_stale_rows(patched):
    missing = _track(created_offset_seconds=100)
    stale_track = _track(created_offset_seconds=50)
    stale_feature = TrackAudioFeature(
        track_id=stale_track.id,
        mfcc=[1.0] * 13,
        mood_tags=[],
        features_version="v1",
    )
    session = FakeFeatureSession(
        [missing, stale_track],
        {stale_track.id: stale_feature},
    )
    patched(session)

    stats = await audio_feature_worker.run_feature_extraction_once()

    assert stats == {"processed": 2, "failed": 0}
    current = settings.audio_feature_current_version
    assert session.features[missing.id].features_version == current
    assert session.features[stale_track.id].features_version == current
    # New v2 JSON columns populated
    for track_id in (missing.id, stale_track.id):
        feature = session.features[track_id]
        assert feature.chroma_vector == [0.3] * 12
        assert feature.mfcc_delta == [0.5] * 13
        assert feature.spectral_contrast == [12.0] * 7
    assert session.commits == 1


@pytest.mark.asyncio
async def test_batch_limit_is_respected(patched):
    tracks = [_track(created_offset_seconds=i) for i in range(10)]
    session = FakeFeatureSession(tracks, {})
    patched(session)

    stats = await audio_feature_worker.run_feature_extraction_once(batch_limit=4)

    assert stats == {"processed": 4, "failed": 0}
    assert len(session.features) == 4


@pytest.mark.asyncio
async def test_up_to_date_rows_are_skipped(patched):
    track = _track()
    session = FakeFeatureSession(
        [track],
        {
            track.id: TrackAudioFeature(
                track_id=track.id,
                mfcc=[1.0] * 13,
                mood_tags=[],
                features_version=settings.audio_feature_current_version,
            )
        },
    )
    patched(session)

    stats = await audio_feature_worker.run_feature_extraction_once()

    assert stats == {"processed": 0, "failed": 0}


@pytest.mark.asyncio
async def test_corrupt_file_does_not_abort_batch(patched):
    good = _track(created_offset_seconds=100, storage_key="good.mp3")
    bad = _track(created_offset_seconds=50, storage_key="bad.mp3")
    good2 = _track(created_offset_seconds=10, storage_key="good2.mp3")
    session = FakeFeatureSession([good, bad, good2], {})

    def flaky_extract(path: Path) -> ExtractedAudioFeatures:
        if path.name == "bad.mp3":
            raise ValueError("corrupt audio")
        return _extracted()

    patched(session, extractor=flaky_extract)

    stats = await audio_feature_worker.run_feature_extraction_once()

    assert stats == {"processed": 2, "failed": 1}
    # The bad track got no feature row; the good ones did.
    assert bad.id not in session.features
    assert good.id in session.features
    assert good2.id in session.features
