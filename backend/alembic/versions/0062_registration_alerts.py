"""Durable registration email alerts.

Revision ID: 0062_registration_alerts
Revises: 0061_matter_custom_fields
"""

import sqlalchemy as sa

from alembic import op

revision = "0062_registration_alerts"
down_revision = "0061_matter_custom_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registration_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("sample_data", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_registration_alerts_deleted_at", "registration_alerts", ["deleted_at"])
    op.create_index(
        "ix_registration_alerts_pending", "registration_alerts", ["sent_at", "next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_table("registration_alerts")
