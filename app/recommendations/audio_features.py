from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    chroma = _float_scalar(np.mean(librosa.feature.chroma_stft(y=y, sr=sr)))
    spectral_centroid = _float_scalar(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    mfcc = [
        _float_scalar(value)
        for value in librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13).mean(axis=1).tolist()
    ]
    return ExtractedAudioFeatures(
        tempo=tempo,
        energy=energy,
        chroma=chroma,
        spectral_centroid=spectral_centroid,
        mfcc=mfcc,
        mood_tags=_infer_mood_tags(tempo=tempo, energy=energy, chroma=chroma),
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
