"""add last_accessed, cover_key to tracks; duration_seconds to float

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00

Bezpieczna dla istniejącej bazy — sprawdza czy kolumny już istnieją
zanim je doda.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade() -> None:
    # last_accessed
    if not _column_exists("tracks", "last_accessed"):
        op.add_column(
            "tracks",
            sa.Column(
                "last_accessed",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_tracks_last_accessed", "tracks", ["last_accessed"])

    # cover_key
    if not _column_exists("tracks", "cover_key"):
        op.add_column("tracks", sa.Column("cover_key", sa.Text(), nullable=True))

    # duration_seconds: Integer → Float (jeśli jeszcze Integer)
    bind = op.get_bind()
    inspector = inspect(bind)
    col_info = {c["name"]: c for c in inspector.get_columns("tracks")}
    if "duration_seconds" in col_info:
        existing_type = str(col_info["duration_seconds"]["type"]).upper()
        if "INT" in existing_type and "FLOAT" not in existing_type:
            op.alter_column(
                "tracks",
                "duration_seconds",
                type_=sa.Float(),
                existing_type=sa.Integer(),
                existing_nullable=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("tracks")]

    if "last_accessed" in cols:
        op.drop_index("ix_tracks_last_accessed", table_name="tracks")
        op.drop_column("tracks", "last_accessed")

    if "cover_key" in cols:
        op.drop_column("tracks", "cover_key")

    op.alter_column(
        "tracks",
        "duration_seconds",
        type_=sa.Integer(),
        existing_type=sa.Float(),
        existing_nullable=True,
    )
