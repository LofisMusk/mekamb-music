"""add per-user libraries and catalog requests

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-10 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_libraries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("api_key_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_libraries_api_key_id", "user_libraries", ["api_key_id"], unique=False
    )

    op.create_table(
        "user_library_tracks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("library_id", sa.UUID(), nullable=False),
        sa.Column("track_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["library_id"], ["user_libraries.id"]),
        sa.ForeignKeyConstraint(["track_id"], ["tracks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("library_id", "track_id", name="uq_user_library_tracks_track"),
    )
    op.create_index(
        "ix_user_library_tracks_library_id", "user_library_tracks", ["library_id"], unique=False
    )
    op.create_index(
        "ix_user_library_tracks_track_id", "user_library_tracks", ["track_id"], unique=False
    )

    op.create_table(
        "catalog_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("api_key_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("foreign_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "foreign_id", name="uq_catalog_requests_kind_foreign_id"),
    )
    op.create_index(
        "ix_catalog_requests_api_key_id", "catalog_requests", ["api_key_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_requests_api_key_id", table_name="catalog_requests")
    op.drop_table("catalog_requests")
    op.drop_index("ix_user_library_tracks_track_id", table_name="user_library_tracks")
    op.drop_index("ix_user_library_tracks_library_id", table_name="user_library_tracks")
    op.drop_table("user_library_tracks")
    op.drop_index("ix_user_libraries_api_key_id", table_name="user_libraries")
    op.drop_table("user_libraries")
