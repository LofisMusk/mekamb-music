from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings


class AudioFeatureExtractionUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractedAudioFeatures:
    tempo: float | None
    energy: float | None
    chroma: float | None
    spectral_centroid: float | None
    mfcc: list[float]
    mood_tags: list[str]
    # ── v2 richer embedding fields ───────────────────────────────────────────
    chroma_vector: list[float]
    mfcc_delta: list[float]
    spectral_contrast: list[float]
    spectral_rolloff: float | None
    spectral_bandwidth: float | None
    zero_crossing_rate: float | None
    harmonic_percussive_ratio: float | None


def extract_audio_features(path: Path, *, duration_seconds: int = 90) -> ExtractedAudioFeatures:
    try:
        import librosa
        import numpy as np
    except ImportError as exc:
        raise AudioFeatureExtractionUnavailable(
            "Install librosa and numpy to extract local audio features."
        ) from exc

    y, sr = librosa.load(path, duration=duration_seconds, mono=True)
    if len(y) == 0:
        raise ValueError(f"Audio file has no readable samples: {path.name}")

    tempo_raw, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = _float_scalar(tempo_raw)
    energy = _float_scalar(np.mean(librosa.feature.rms(y=y)))

    chroma_matrix = librosa.feature.chroma_stft(y=y, sr=sr)
    chroma = _float_scalar(np.mean(chroma_matrix))
    chroma_vector = [_float_scalar(value) for value in chroma_matrix.mean(axis=1).tolist()]

    spectral_centroid = _float_scalar(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))

    # Compute the MFCC matrix once and derive both the mean vector and its delta.
    mfcc_matrix = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc = [_float_scalar(value) for value in mfcc_matrix.mean(axis=1).tolist()]
    mfcc_delta = [
        _float_scalar(value)
        for value in librosa.feature.delta(mfcc_matrix).mean(axis=1).tolist()
    ]

    spectral_contrast = [
        _float_scalar(value)
        for value in librosa.feature.spectral_contrast(y=y, sr=sr).mean(axis=1).tolist()
    ]
    spectral_rolloff = _float_scalar(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr)))
    spectral_bandwidth = _float_scalar(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr)))
    zero_crossing_rate = _float_scalar(np.mean(librosa.feature.zero_crossing_rate(y=y)))

    harmonic_percussive_ratio: float | None = None
    if settings.audio_feature_enable_hpss:
        # HPSS is the most CPU-expensive addition — gate it behind config.
        y_harmonic, y_percussive = librosa.effects.hpss(y=y)
        harmonic_percussive_ratio = _float_scalar(
            (np.mean(np.abs(y_harmonic)) + 1e-9) / (np.mean(np.abs(y_percussive)) + 1e-9)
        )

    return ExtractedAudioFeatures(
        tempo=tempo,
        energy=energy,
        chroma=chroma,
        spectral_centroid=spectral_centroid,
        mfcc=mfcc,
        mood_tags=_infer_mood_tags(tempo=tempo, energy=energy, chroma=chroma),
        chroma_vector=chroma_vector,
        mfcc_delta=mfcc_delta,
        spectral_contrast=spectral_contrast,
        spectral_rolloff=spectral_rolloff,
        spectral_bandwidth=spectral_bandwidth,
        zero_crossing_rate=zero_crossing_rate,
        harmonic_percussive_ratio=harmonic_percussive_ratio,
    )


def _infer_mood_tags(*, tempo: float | None, energy: float | None, chroma: float | None) -> list[str]:
    tags: list[str] = []
    if tempo is not None:
        if tempo >= 135:
            tags.append("fast")
        elif tempo <= 85:
            tags.append("slow")
        else:
            tags.append("midtempo")
    if energy is not None:
        if energy >= 0.12:
            tags.append("high_energy")
        elif energy <= 0.04:
            tags.append("calm")
    if chroma is not None and chroma >= 0.45:
        tags.append("harmonic")
    return tags


def _float_scalar(value: object) -> float:
    try:
        if hasattr(value, "item"):
            return float(value.item())
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Could not convert audio feature value to float: {value!r}") from exc
