"""Outreach follow-ups: the one automatic reminder a week after an opened-but-unclicked
invitation, and personal notes the admin sends from the Warm leads list.

Revision ID: 0093_outreach_followups
Revises: 0092_daily_brief_email
"""

import sqlalchemy as sa

from alembic import op

revision = "0093_outreach_followups"
down_revision = "0092_daily_brief_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outreach_followups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("subject", sa.String(200)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sent_by", sa.Uuid()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outreach_followups_contact_id", "outreach_followups", ["contact_id"])
    op.create_index("ix_outreach_followups_sent_at", "outreach_followups", ["sent_at"])


def downgrade() -> None:
    op.drop_index("ix_outreach_followups_sent_at", table_name="outreach_followups")
    op.drop_index("ix_outreach_followups_contact_id", table_name="outreach_followups")
    op.drop_table("outreach_followups")
