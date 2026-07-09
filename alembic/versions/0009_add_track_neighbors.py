"""add track neighbors

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-09 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "track_neighbors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("track_id", sa.UUID(), nullable=False),
        sa.Column("neighbor_track_id", sa.UUID(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("co_play_count", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["track_id"], ["tracks.id"]),
        sa.ForeignKeyConstraint(["neighbor_track_id"], ["tracks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "track_id", "neighbor_track_id", name="uq_track_neighbors_pair"
        ),
    )
    op.create_index(
        "ix_track_neighbors_track_id", "track_neighbors", ["track_id"]
    )
    op.create_index(
        "ix_track_neighbors_neighbor_track_id", "track_neighbors", ["neighbor_track_id"]
    )
    op.create_index(
        "ix_track_neighbors_computed_at", "track_neighbors", ["computed_at"]
    )
    op.create_index(
        "ix_track_neighbors_track_id_score", "track_neighbors", ["track_id", "score"]
    )


def downgrade() -> None:
    op.drop_index("ix_track_neighbors_track_id_score", table_name="track_neighbors")
    op.drop_index("ix_track_neighbors_computed_at", table_name="track_neighbors")
    op.drop_index("ix_track_neighbors_neighbor_track_id", table_name="track_neighbors")
    op.drop_index("ix_track_neighbors_track_id", table_name="track_neighbors")
    op.drop_table("track_neighbors")
