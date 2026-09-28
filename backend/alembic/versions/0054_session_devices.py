"""Identify browser installations so repeat sign-ins replace stale sessions.

Revision ID: 0054_session_devices
Revises: 0053_draft_templates
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0054_session_devices"
down_revision: str | None = "0053_draft_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("device_id", sa.String(64), nullable=True))
    op.create_index("ix_refresh_tokens_device_id", "refresh_tokens", ["device_id"])
    op.create_index(
        "ix_refresh_tokens_user_device", "refresh_tokens", ["user_id", "device_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_device", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_device_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "device_id")
