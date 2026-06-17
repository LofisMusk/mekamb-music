"""add personalization signals

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-17 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("personalization_signals"):
        return

    op.create_table(
        "personalization_signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("track_id", sa.UUID(), nullable=False),
        sa.Column("signal_type", sa.String(length=32), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="api"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["track_id"], ["tracks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personalization_signals_created_at", "personalization_signals", ["created_at"])
    op.create_index("ix_personalization_signals_signal_type", "personalization_signals", ["signal_type"])
    op.create_index("ix_personalization_signals_source", "personalization_signals", ["source"])
    op.create_index("ix_personalization_signals_track_id", "personalization_signals", ["track_id"])


def downgrade() -> None:
    if not _table_exists("personalization_signals"):
        return

    op.drop_index("ix_personalization_signals_track_id", table_name="personalization_signals")
    op.drop_index("ix_personalization_signals_source", table_name="personalization_signals")
    op.drop_index("ix_personalization_signals_signal_type", table_name="personalization_signals")
    op.drop_index("ix_personalization_signals_created_at", table_name="personalization_signals")
    op.drop_table("personalization_signals")
