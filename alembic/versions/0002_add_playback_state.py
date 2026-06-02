"""add cross-session playback state

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-02 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("playback_states"):
        op.create_table(
            "playback_states",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("current_track_id", sa.UUID(), nullable=True),
            sa.Column("position_seconds", sa.Float(), nullable=False, server_default="0"),
            sa.Column("is_playing", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("repeat_mode", sa.String(length=32), nullable=False, server_default="off"),
            sa.Column("shuffle", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("active_device_id", sa.String(length=255), nullable=True),
            sa.Column("active_device_name", sa.String(length=255), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(["current_track_id"], ["tracks.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_playback_states_current_track_id", "playback_states", ["current_track_id"])
        op.create_index("ix_playback_states_updated_at", "playback_states", ["updated_at"])

    if not _table_exists("playback_queue_items"):
        op.create_table(
            "playback_queue_items",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("state_id", sa.String(length=64), nullable=False),
            sa.Column("track_id", sa.UUID(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column(
                "added_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(["state_id"], ["playback_states.id"]),
            sa.ForeignKeyConstraint(["track_id"], ["tracks.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("state_id", "position", name="uq_playback_queue_position"),
        )
        op.create_index("ix_playback_queue_items_state_id", "playback_queue_items", ["state_id"])
        op.create_index("ix_playback_queue_items_track_id", "playback_queue_items", ["track_id"])


def downgrade() -> None:
    if _table_exists("playback_queue_items"):
        op.drop_index("ix_playback_queue_items_track_id", table_name="playback_queue_items")
        op.drop_index("ix_playback_queue_items_state_id", table_name="playback_queue_items")
        op.drop_table("playback_queue_items")

    if _table_exists("playback_states"):
        op.drop_index("ix_playback_states_updated_at", table_name="playback_states")
        op.drop_index("ix_playback_states_current_track_id", table_name="playback_states")
        op.drop_table("playback_states")
