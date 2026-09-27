"""Notification channels: per-user preferences (rule engine) + delivery log.

Both tables are global (like ``notifications`` itself) — keyed by ``user_id``,
no tenant scoping / RLS.

Revision ID: 0024_notif_channels
Revises: 0023_marketplace
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_notif_channels"
down_revision: str | None = "0023_marketplace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("types", sa.JSON(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "channel", name="uq_notif_pref_user_channel"),
    )
    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"])

    op.create_table(
        "notification_deliveries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("detail", sa.String(400), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.drop_table("notification_preferences")
