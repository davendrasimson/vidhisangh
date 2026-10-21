"""First-party sign-up funnel: one counter per step per day (no personal data).

Revision ID: 0073_funnel_daily
Revises: 0072_push_devices
"""

import sqlalchemy as sa

from alembic import op

revision = "0073_funnel_daily"
down_revision = "0072_push_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "funnel_daily",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("step", sa.String(40), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("day", "step", name="uq_funnel_daily_day_step"),
    )


def downgrade() -> None:
    op.drop_table("funnel_daily")
