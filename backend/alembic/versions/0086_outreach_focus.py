"""Outreach: a court-by-court focus for the invitation campaign.

Revision ID: 0086_outreach_focus
Revises: 0085_identity_audience

Owner's decision, 2 Nov 2026: invitations go out one bar at a time so that a
new member finds colleagues from their own court. ``outreach_settings.focus``
holds a city or court name; while set, the daily batch and "Send now" take only
contacts whose city or court matches it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0086_outreach_focus"
down_revision = "0085_identity_audience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outreach_settings", sa.Column("focus", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("outreach_settings", "focus")
