"""WhatsApp consent ledger gains a ``topic``: ``updates`` (product updates, the
existing rows) or ``daily`` (VidhiSangh Daily every morning). Each topic is a
separate choice: a yes to one never covers the other.

Revision ID: 0090_whatsapp_consent_topic
Revises: 0089_daily_brief
"""

import sqlalchemy as sa

from alembic import op

revision = "0090_whatsapp_consent_topic"
down_revision = "0089_daily_brief"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_updates_consents",
        sa.Column("topic", sa.String(20), nullable=False, server_default="updates"),
    )
    op.create_index("ix_whatsapp_updates_consents_user_topic", "whatsapp_updates_consents", ["user_id", "topic"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_updates_consents_user_topic", table_name="whatsapp_updates_consents")
    op.drop_column("whatsapp_updates_consents", "topic")
