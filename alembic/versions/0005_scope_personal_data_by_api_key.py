"""scope personal data by api key

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-17 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_API_KEY_ID = "default"


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
    for table in (
        "liked_tracks",
        "track_plays",
        "personalization_signals",
        "user_actions",
        "playlists",
    ):
        if not _table_exists(table):
            continue
        if not _column_exists(table, "api_key_id"):
            op.add_column(
                table,
                sa.Column(
                    "api_key_id",
                    sa.String(length=64),
                    nullable=False,
                    server_default=DEFAULT_API_KEY_ID,
                ),
            )
        index_name = f"ix_{table}_api_key_id"
        if not _index_exists(table, index_name):
            op.create_index(index_name, table, ["api_key_id"])

    if _table_exists("liked_tracks"):
        try:
            op.drop_constraint("uq_liked_tracks_track", "liked_tracks", type_="unique")
        except Exception:
            pass
        try:
            op.create_unique_constraint(
                "uq_liked_tracks_api_key_track",
                "liked_tracks",
                ["api_key_id", "track_id"],
            )
        except Exception:
            pass


def downgrade() -> None:
    if _table_exists("liked_tracks"):
        try:
            op.drop_constraint("uq_liked_tracks_api_key_track", "liked_tracks", type_="unique")
        except Exception:
            pass
        try:
            op.create_unique_constraint("uq_liked_tracks_track", "liked_tracks", ["track_id"])
        except Exception:
            pass

    for table in (
        "playlists",
        "user_actions",
        "personalization_signals",
        "track_plays",
        "liked_tracks",
    ):
        if not _table_exists(table) or not _column_exists(table, "api_key_id"):
            continue
        index_name = f"ix_{table}_api_key_id"
        if _index_exists(table, index_name):
            op.drop_index(index_name, table_name=table)
        op.drop_column(table, "api_key_id")
