"""add infinite play audio features

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-20 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table in inspector.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return index_name in [idx["name"] for idx in inspector.get_indexes(table)]


def upgrade() -> None:
    if _table_exists("track_plays"):
        if not _column_exists("track_plays", "completed"):
            op.add_column(
                "track_plays",
                sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.true()),
            )
        if not _column_exists("track_plays", "listen_ratio"):
            op.add_column("track_plays", sa.Column("listen_ratio", sa.Float(), nullable=True))
        if not _column_exists("track_plays", "source"):
            op.add_column(
                "track_plays",
                sa.Column("source", sa.String(length=64), nullable=False, server_default="api"),
            )
        for index_name, column in (
            ("ix_track_plays_completed", "completed"),
            ("ix_track_plays_source", "source"),
        ):
            if not _index_exists("track_plays", index_name):
                op.create_index(index_name, "track_plays", [column])

    if not _table_exists("track_audio_features"):
        op.create_table(
            "track_audio_features",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("track_id", sa.UUID(), nullable=False),
            sa.Column("tempo", sa.Float(), nullable=True),
            sa.Column("energy", sa.Float(), nullable=True),
            sa.Column("chroma", sa.Float(), nullable=True),
            sa.Column("spectral_centroid", sa.Float(), nullable=True),
            sa.Column("mfcc", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("mood_tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("extractor", sa.String(length=64), nullable=False, server_default="local"),
            sa.Column("features_version", sa.String(length=32), nullable=False, server_default="v1"),
            sa.Column(
                "extracted_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(["track_id"], ["tracks.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("track_id", name="uq_track_audio_features_track"),
        )
        op.create_index("ix_track_audio_features_track_id", "track_audio_features", ["track_id"])
        op.create_index(
            "ix_track_audio_features_extracted_at",
            "track_audio_features",
            ["extracted_at"],
        )


def downgrade() -> None:
    if _table_exists("track_audio_features"):
        op.drop_index("ix_track_audio_features_extracted_at", table_name="track_audio_features")
        op.drop_index("ix_track_audio_features_track_id", table_name="track_audio_features")
        op.drop_table("track_audio_features")

    if _table_exists("track_plays"):
        for index_name in ("ix_track_plays_source", "ix_track_plays_completed"):
            if _index_exists("track_plays", index_name):
                op.drop_index(index_name, table_name="track_plays")
        for column in ("source", "listen_ratio", "completed"):
            if _column_exists("track_plays", column):
                op.drop_column("track_plays", column)
