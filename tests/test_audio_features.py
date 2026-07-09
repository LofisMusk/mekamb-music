import math
import wave
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from app.db.models import TrackAudioFeature
from app.recommendations.audio_features import extract_audio_features
from app.recommendations.engine import (
    _cosine_similarity,
    _normalized_audio_vector,
)


def _write_sine_wav(path: Path, *, freq: float = 440.0, seconds: float = 2.0, sr: int = 22_050) -> None:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    samples = (0.5 * np.sin(2 * math.pi * freq * t)).astype(np.float32)
    pcm = np.int16(samples * 32767)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(pcm.tobytes())


def test_extract_audio_features_returns_v2_fields_with_expected_lengths(tmp_path: Path):
    wav = tmp_path / "sine.wav"
    _write_sine_wav(wav)

    features = extract_audio_features(wav)

    # v1 fields still present
    assert len(features.mfcc) == 13
    assert features.tempo is not None
    assert features.energy is not None

    # v2 richer fields with expected lengths
    assert len(features.chroma_vector) == 12
    assert len(features.mfcc_delta) == 13
    assert len(features.spectral_contrast) == 7
    assert features.spectral_rolloff is not None
    assert features.spectral_bandwidth is not None
    assert features.zero_crossing_rate is not None
    # HPSS enabled by default in settings
    assert features.harmonic_percussive_ratio is not None


def test_extract_audio_features_skips_hpss_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.recommendations import audio_features as module

    monkeypatch.setattr(module.settings, "audio_feature_enable_hpss", False)
    wav = tmp_path / "sine.wav"
    _write_sine_wav(wav)

    features = extract_audio_features(wav)

    assert features.harmonic_percussive_ratio is None
    # everything else still extracted
    assert len(features.chroma_vector) == 12


def _v1_feature(*, mfcc: list[float], tempo: float, energy: float, chroma: float, centroid: float) -> TrackAudioFeature:
    return TrackAudioFeature(
        track_id=uuid4(),
        tempo=tempo,
        energy=energy,
        chroma=chroma,
        spectral_centroid=centroid,
        mfcc=mfcc,
        mood_tags=[],
    )


def _legacy_v1_vector(feature: TrackAudioFeature) -> list[float]:
    """The carried-over dimensions of the pre-existing vector builder (regression
    baseline). The scalar ``chroma`` mean was intentionally dropped in the v2 builder
    in favor of the 12-bin ``chroma_vector`` (all-zero for v1 rows), so it is excluded
    here as well — everything else must contribute identically to v1-v1 similarity."""
    mfcc = list(feature.mfcc or [])[:13]
    while len(mfcc) < 13:
        mfcc.append(0.0)
    return [
        *(float(value) / 100.0 for value in mfcc),
        float(feature.tempo or 0.0) / 220.0,
        float(feature.energy or 0.0),
        float(feature.spectral_centroid or 0.0) / 8_000.0,
    ]


def test_version_aware_vector_is_fixed_length_for_v1_and_v2():
    v1 = _v1_feature(mfcc=[10.0] * 13, tempo=120, energy=0.09, chroma=0.45, centroid=2200)
    v2 = TrackAudioFeature(
        track_id=uuid4(),
        tempo=120,
        energy=0.09,
        chroma=0.45,
        spectral_centroid=2200,
        mfcc=[10.0] * 13,
        mood_tags=[],
        chroma_vector=[0.3] * 12,
        mfcc_delta=[0.5] * 13,
        spectral_contrast=[12.0] * 7,
        spectral_rolloff=3200.0,
        spectral_bandwidth=1800.0,
        zero_crossing_rate=0.08,
        harmonic_percussive_ratio=1.4,
    )

    v1_vector = _normalized_audio_vector(v1)
    v2_vector = _normalized_audio_vector(v2)

    assert len(v1_vector) == len(v2_vector) == 52


def test_v1_padded_cosine_matches_legacy_17_dim_behavior():
    seed = _v1_feature(mfcc=[10.0] * 13, tempo=122, energy=0.09, chroma=0.45, centroid=2200)
    other = _v1_feature(mfcc=[10.5] * 13, tempo=124, energy=0.10, chroma=0.44, centroid=2300)

    legacy_similarity = _cosine_similarity(_legacy_v1_vector(seed), _legacy_v1_vector(other))
    new_similarity = _cosine_similarity(
        _normalized_audio_vector(seed), _normalized_audio_vector(other)
    )

    # Padding with cosine-invariant zeros must not change v1-v1 similarity.
    assert new_similarity == pytest.approx(legacy_similarity, rel=1e-9, abs=1e-9)
