"""Outreach contacts: mobile number and the "asked to be removed" flag.

Revision ID: 0084_outreach_contact_fields
Revises: 0083_judicial_officer_code

The admin's contacts list shows who was approached and when; a person who
asks to be taken off (by reply, call or grievance) is flagged
``removal_requested`` (status, timestamp, note) and suppressed like an
unsubscribe. ``mobile`` is kept for lists that publish it (never used for
sending; WhatsApp outreach would need its own consent path).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0084_outreach_contact_fields"
down_revision = "0083_judicial_officer_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outreach_contacts", sa.Column("mobile", sa.String(20), nullable=True))
    op.add_column("outreach_contacts", sa.Column("removal_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outreach_contacts", sa.Column("removal_note", sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column("outreach_contacts", "removal_note")
    op.drop_column("outreach_contacts", "removal_requested_at")
    op.drop_column("outreach_contacts", "mobile")
