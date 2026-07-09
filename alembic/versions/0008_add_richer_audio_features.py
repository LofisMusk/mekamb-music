"""add richer audio features

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-09 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("track_audio_features", sa.Column("chroma_vector", sa.JSON(), nullable=True))
    op.add_column("track_audio_features", sa.Column("mfcc_delta", sa.JSON(), nullable=True))
    op.add_column("track_audio_features", sa.Column("spectral_contrast", sa.JSON(), nullable=True))
    op.add_column("track_audio_features", sa.Column("spectral_rolloff", sa.Float(), nullable=True))
    op.add_column("track_audio_features", sa.Column("spectral_bandwidth", sa.Float(), nullable=True))
    op.add_column("track_audio_features", sa.Column("zero_crossing_rate", sa.Float(), nullable=True))
    op.add_column(
        "track_audio_features",
        sa.Column("harmonic_percussive_ratio", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("track_audio_features", "harmonic_percussive_ratio")
    op.drop_column("track_audio_features", "zero_crossing_rate")
    op.drop_column("track_audio_features", "spectral_bandwidth")
    op.drop_column("track_audio_features", "spectral_rolloff")
    op.drop_column("track_audio_features", "spectral_contrast")
    op.drop_column("track_audio_features", "mfcc_delta")
    op.drop_column("track_audio_features", "chroma_vector")
