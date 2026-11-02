"""Official daily orders, email opt-in and durable daily delivery claims."""

import sqlalchemy as sa

from alembic import op

revision = "0088_sc_daily_orders"
down_revision = "0087_outreach_engagement"
branch_labels = None
depends_on = None


def audit_columns():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    ]


def upgrade():
    op.create_table(
        "sc_daily_orders",
        *audit_columns(),
        sa.Column(
            "judgment_id",
            sa.Uuid(),
            sa.ForeignKey("judgments.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("source_url", sa.String(1000), nullable=False, unique=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_sha256", sa.String(64)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error", sa.String(200)),
    )
    op.create_index("ix_sc_daily_orders_first_seen_at", "sc_daily_orders", ["first_seen_at"])
    op.create_index("ix_sc_daily_orders_status", "sc_daily_orders", ["status"])
    op.create_table(
        "sc_daily_subscriptions",
        *audit_columns(),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
    )
    op.create_table(
        "sc_daily_emails",
        *audit_columns(),
        sa.Column(
            "subscription_id",
            sa.Uuid(),
            sa.ForeignKey("sc_daily_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("judgment_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint("subscription_id", "for_date", name="uq_sc_daily_email_day"),
    )
    op.create_index("ix_sc_daily_emails_subscription_id", "sc_daily_emails", ["subscription_id"])


def downgrade():
    for table in ("sc_daily_emails", "sc_daily_subscriptions", "sc_daily_orders"):
        op.drop_table(table)
