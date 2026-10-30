"""Judicial officer code on the profile.

Revision ID: 0083_judicial_officer_code
Revises: 0082_recurring_invoices

The e-Courts officer identifier a sitting judge writes on every order — the
JO code in Allahabad / Uttarakhand practice, the UID No. in Punjab & Haryana
practice. Stored once on the profile so order headings and signature blocks
fill it in instead of it being typed each time.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0083_judicial_officer_code"
down_revision = "0082_recurring_invoices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("professional_profiles", sa.Column("judicial_officer_code", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("professional_profiles", "judicial_officer_code")
