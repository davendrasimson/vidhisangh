"""Network post reports and timed posting moderation.

Revision ID: 0057_network_moderation
Revises: 0056_platform_support
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0057_network_moderation"
down_revision: str | None = "0056_platform_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("posting_restricted_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users", sa.Column("network_profile_removed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_users_posting_restricted_until", "users", ["posting_restricted_until"]
    )
    op.add_column(
        "support_tickets", sa.Column("reported_post_id", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.add_column(
        "support_tickets", sa.Column("reported_user_id", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.add_column("support_tickets", sa.Column("report_context", sa.JSON(), nullable=True))
    op.create_index("ix_support_tickets_reported_post_id", "support_tickets", ["reported_post_id"])
    op.create_index("ix_support_tickets_reported_user_id", "support_tickets", ["reported_user_id"])


def downgrade() -> None:
    op.drop_index("ix_support_tickets_reported_user_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_reported_post_id", table_name="support_tickets")
    op.drop_column("support_tickets", "report_context")
    op.drop_column("support_tickets", "reported_user_id")
    op.drop_column("support_tickets", "reported_post_id")
    op.drop_index("ix_users_posting_restricted_until", table_name="users")
    op.drop_column("users", "network_profile_removed_at")
    op.drop_column("users", "posting_restricted_until")
