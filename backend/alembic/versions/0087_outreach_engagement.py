"""Outreach: delivery, open, click and complaint times per invitation.

Revision ID: 0087_outreach_engagement
Revises: 0086_outreach_focus

Owner's request, 2 Nov 2026: see who reads the invitation and who joins
through it. The join link now carries the contact's token and is recorded
before redirecting; a tracking image records opens; the relay's webhook
(Brevo) reports delivery, bounces and complaints.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0087_outreach_engagement"
down_revision = "0086_outreach_focus"
branch_labels = None
depends_on = None

COLUMNS = ("delivered_at", "opened_at", "clicked_at", "complained_at")


def upgrade() -> None:
    for name in COLUMNS:
        op.add_column("outreach_contacts", sa.Column(name, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for name in reversed(COLUMNS):
        op.drop_column("outreach_contacts", name)
