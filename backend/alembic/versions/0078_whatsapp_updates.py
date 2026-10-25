"""WhatsApp product updates: the member's consent and a per-campaign send log.

Global tables (no RLS), like the notification preferences and hearing-reminder
log they sit beside. The consent is an append-only ledger written by the
member (Settings, or the Home card); the send log only by the
``whatsapp_updates`` job.

Revision ID: 0078_whatsapp_updates
Revises: 0077_ai_headnote_search
"""

import sqlalchemy as sa

from alembic import op

revision = "0078_whatsapp_updates"
down_revision = "0077_ai_headnote_search"
branch_labels = None
depends_on = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "whatsapp_updates_consents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("notice_version", sa.String(20), nullable=True),
        sa.Column("ip_coarse", sa.String(64), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        *_audit_columns(),
    )
    op.create_index("ix_whatsapp_updates_consents_user_id", "whatsapp_updates_consents", ["user_id"])
    op.create_table(
        "whatsapp_campaign_sends",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("campaign", sa.String(60), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("phone_hash", sa.String(64), nullable=False),
        sa.Column("template", sa.String(60), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("basis", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("detail", sa.String(200), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("campaign", "phone_hash", name="uq_whatsapp_campaign_phone"),
    )
    op.create_index("ix_whatsapp_campaign_sends_campaign", "whatsapp_campaign_sends", ["campaign"])
    op.create_index("ix_whatsapp_campaign_sends_user_id", "whatsapp_campaign_sends", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_campaign_sends_user_id", table_name="whatsapp_campaign_sends")
    op.drop_index("ix_whatsapp_campaign_sends_campaign", table_name="whatsapp_campaign_sends")
    op.drop_table("whatsapp_campaign_sends")
    op.drop_index("ix_whatsapp_updates_consents_user_id", table_name="whatsapp_updates_consents")
    op.drop_table("whatsapp_updates_consents")
