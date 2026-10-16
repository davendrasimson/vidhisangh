"""Outreach: invitation emails to non-members, with a permanent suppression list.

Global tables (no RLS), reached only by the platform admin and the daily
sender job. Sending starts paused.

Revision ID: 0067_outreach
Revises: 0066_post_rich_text_images
"""

import sqlalchemy as sa

from alembic import op

revision = "0067_outreach"
down_revision = "0066_post_rich_text_images"
branch_labels = None
depends_on = None

UUID = sa.Uuid(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "outreach_contacts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("court", sa.String(200), nullable=True),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined_user_id", UUID, nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("email", name="uq_outreach_contacts_email"),
        sa.UniqueConstraint("token", name="uq_outreach_contacts_token"),
    )
    op.create_index("ix_outreach_contacts_status", "outreach_contacts", ["status"])
    op.create_table(
        "outreach_suppressions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email_hash", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("email_hash", name="uq_outreach_suppressions_hash"),
    )
    op.create_table(
        "outreach_settings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="50"),
        *_timestamps(),
    )


def downgrade() -> None:
    op.drop_table("outreach_settings")
    op.drop_table("outreach_suppressions")
    op.drop_table("outreach_contacts")
