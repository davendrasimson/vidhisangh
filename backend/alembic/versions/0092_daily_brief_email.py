"""VidhiSangh Daily by email: the per-member preference (default on for members
without the app) with its one-tap unsubscribe token, and the send log.

Revision ID: 0092_daily_brief_email
Revises: 0091_court_cause_lists
"""

import sqlalchemy as sa

from alembic import op

revision = "0092_daily_brief_email"
down_revision = "0091_court_cause_lists"
branch_labels = None
depends_on = None


def audit_columns():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    ]


def upgrade() -> None:
    op.create_table(
        "daily_brief_email_prefs",
        *audit_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
    )
    op.create_table(
        "daily_brief_emails",
        *audit_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("lead", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("detail", sa.String(200)),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "for_date", name="uq_daily_brief_email_user_day"),
    )
    op.create_index("ix_daily_brief_emails_user_id", "daily_brief_emails", ["user_id"])
    op.create_index("ix_daily_brief_emails_for_date", "daily_brief_emails", ["for_date"])


def downgrade() -> None:
    op.drop_index("ix_daily_brief_emails_for_date", table_name="daily_brief_emails")
    op.drop_index("ix_daily_brief_emails_user_id", table_name="daily_brief_emails")
    op.drop_table("daily_brief_emails")
    op.drop_table("daily_brief_email_prefs")
