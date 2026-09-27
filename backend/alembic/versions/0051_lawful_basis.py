"""Lawful basis on matter parties and CRM leads (DPDP s.4/s.7, audit P-5).

Revision ID: 0051_lawful_basis
Revises: 0050_auth_hardening
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0051_lawful_basis"
down_revision: str | None = "0050_auth_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("matter_parties", "leads"):
        with op.batch_alter_table(table) as b:
            b.add_column(sa.Column("lawful_basis", sa.String(20), nullable=False, server_default="legitimate_use"))
            b.add_column(sa.Column("basis_note", sa.String(300), nullable=True))


def downgrade() -> None:
    for table in ("leads", "matter_parties"):
        with op.batch_alter_table(table) as b:
            b.drop_column("basis_note")
            b.drop_column("lawful_basis")
