"""
Audio feature worker — automatycznie ekstrahuje cechy audio (librosa) dla trackow,
ktore nie maja jeszcze wiersza TrackAudioFeature lub maja przestarzala features_version.

Uruchamiany jako background asyncio task w FastAPI (run_feature_extraction_loop),
lub standalone: python -m app.workers.audio_feature_worker
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import or_, select

from app.core.config import settings
from app.db.models import Track, TrackAudioFeature, utcnow
from app.db.session import AsyncSessionLocal, init_db
from app.recommendations.audio_features import extract_audio_features
from app.storage.library import build_library_storage

logger = logging.getLogger(__name__)


async def run_feature_extraction_once(*, batch_limit: int | None = None) -> dict[str, int]:
    """
    Jednorazowa ekstrakcja cech audio dla backlogu trackow. Zwraca statystyki.
    """
    if batch_limit is None:
        batch_limit = settings.audio_feature_batch_size

    processed = 0
    failed = 0

    async with AsyncSessionLocal() as session:
        # Tracki bez wiersza cech LUB z przestarzala wersja — outer join + IS NULL /
        # version-mismatch. Najstarsze created_at najpierw, ograniczone do batch_limit.
        rows = list(
            await session.scalars(
                select(Track)
                .outerjoin(TrackAudioFeature, TrackAudioFeature.track_id == Track.id)
                .where(
                    or_(
                        TrackAudioFeature.id.is_(None),
                        TrackAudioFeature.features_version
                        != settings.audio_feature_current_version,
                    )
                )
                .order_by(Track.created_at.asc())
                .limit(batch_limit)
            )
        )
        if not rows:
            logger.info("Audio feature worker: nic do przetworzenia.")
            return {"processed": 0, "failed": 0}

        storage = build_library_storage(settings)
        for track in rows:
            try:
                path = storage.ensure_cached(track.storage_key)
                extracted = await asyncio.to_thread(extract_audio_features, path)

                feature = await session.scalar(
                    select(TrackAudioFeature).where(TrackAudioFeature.track_id == track.id)
                )
                if feature is None:
                    feature = TrackAudioFeature(track_id=track.id)
                    session.add(feature)
                feature.tempo = extracted.tempo
                feature.energy = extracted.energy
                feature.chroma = extracted.chroma
                feature.spectral_centroid = extracted.spectral_centroid
                feature.mfcc = extracted.mfcc
                feature.mood_tags = extracted.mood_tags
                feature.chroma_vector = extracted.chroma_vector
                feature.mfcc_delta = extracted.mfcc_delta
                feature.spectral_contrast = extracted.spectral_contrast
                feature.spectral_rolloff = extracted.spectral_rolloff
                feature.spectral_bandwidth = extracted.spectral_bandwidth
                feature.zero_crossing_rate = extracted.zero_crossing_rate
                feature.harmonic_percussive_ratio = extracted.harmonic_percussive_ratio
                feature.extractor = "librosa"
                feature.features_version = settings.audio_feature_current_version
                feature.extracted_at = utcnow()
                processed += 1
            except Exception as exc:
                # Jeden zepsuty plik nie moze przerwac calego batcha.
                failed += 1
                logger.warning(
                    "Audio feature extraction failed for track %s (%s): %s",
                    track.id, track.storage_key, exc,
                )

        await session.commit()

    logger.info("Audio feature worker: processed=%d, failed=%d.", processed, failed)
    return {"processed": processed, "failed": failed}


async def run_feature_extraction_loop() -> None:
    """Nieskończona pętla — uruchamiana jako FastAPI background task."""
    while True:
        await asyncio.sleep(settings.audio_feature_worker_interval_seconds)
        try:
            stats = await run_feature_extraction_once()
            logger.info("Audio feature loop stats: %s", stats)
        except Exception as exc:
            logger.error("Audio feature worker loop error: %s", exc, exc_info=True)


async def _main() -> None:
    await init_db()
    stats = await run_feature_extraction_once()
    print(stats)


if __name__ == "__main__":
    asyncio.run(_main())
