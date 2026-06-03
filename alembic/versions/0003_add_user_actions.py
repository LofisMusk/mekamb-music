"""add user action sync log

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-03 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("user_actions"):
        return

    op.create_table(
        "user_actions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("origin_instance_id", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("apply_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_actions_action_type", "user_actions", ["action_type"])
    op.create_index("ix_user_actions_applied_at", "user_actions", ["applied_at"])
    op.create_index("ix_user_actions_created_at", "user_actions", ["created_at"])
    op.create_index("ix_user_actions_entity_id", "user_actions", ["entity_id"])
    op.create_index("ix_user_actions_entity_type", "user_actions", ["entity_type"])
    op.create_index("ix_user_actions_origin_instance_id", "user_actions", ["origin_instance_id"])


def downgrade() -> None:
    if not _table_exists("user_actions"):
        return

    op.drop_index("ix_user_actions_origin_instance_id", table_name="user_actions")
    op.drop_index("ix_user_actions_entity_type", table_name="user_actions")
    op.drop_index("ix_user_actions_entity_id", table_name="user_actions")
    op.drop_index("ix_user_actions_created_at", table_name="user_actions")
    op.drop_index("ix_user_actions_applied_at", table_name="user_actions")
    op.drop_index("ix_user_actions_action_type", table_name="user_actions")
    op.drop_table("user_actions")
