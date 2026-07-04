"""add search and history indexes

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-04 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return index_name in [idx["name"] for idx in inspector.get_indexes(table)]


_TRGM_INDEXES = (
    ("ix_tracks_title_trgm", "tracks", "title"),
    ("ix_tracks_artist_trgm", "tracks", "artist"),
    ("ix_tracks_album_trgm", "tracks", "album"),
    ("ix_tracks_original_filename_trgm", "tracks", "original_filename"),
)

_BTREE_INDEXES = (
    ("ix_tracks_created_at", "tracks", ["created_at"]),
    ("ix_playlists_updated_at", "playlists", ["updated_at"]),
    ("ix_track_plays_api_key_id_played_at", "track_plays", ["api_key_id", "played_at"]),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    for index_name, table, column in _TRGM_INDEXES:
        if not _index_exists(table, index_name):
            op.create_index(
                index_name,
                table,
                [column],
                postgresql_using="gin",
                postgresql_ops={column: "gin_trgm_ops"},
            )

    for index_name, table, columns in _BTREE_INDEXES:
        if not _index_exists(table, index_name):
            op.create_index(index_name, table, columns)


def downgrade() -> None:
    for index_name, table, _columns in _BTREE_INDEXES:
        if _index_exists(table, index_name):
            op.drop_index(index_name, table_name=table)

    for index_name, table, _column in _TRGM_INDEXES:
        if _index_exists(table, index_name):
            op.drop_index(index_name, table_name=table)
