"""Evening WhatsApp hearing reminders: one row per member per day.

Global table (no RLS), like the notification preferences it goes with;
written only by the reminder job.

Revision ID: 0068_hearing_reminders
Revises: 0067_outreach
"""

import sqlalchemy as sa

from alembic import op

revision = "0068_hearing_reminders"
down_revision = "0067_outreach"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hearing_reminder_sends",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("hearing_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("detail", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "for_date", name="uq_hearing_reminder_user_day"),
    )
    op.create_index("ix_hearing_reminder_sends_user_id", "hearing_reminder_sends", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_hearing_reminder_sends_user_id", table_name="hearing_reminder_sends")
    op.drop_table("hearing_reminder_sends")
