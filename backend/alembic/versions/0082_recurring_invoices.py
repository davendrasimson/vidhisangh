"""Recurring invoices: the template carries its cadence, the sweep raises draft copies.

Revision ID: 0082_recurring_invoices
Revises: 0081_board_digest_sends

``recurrence`` (monthly | quarterly | yearly) with ``recur_until`` marks an
invoice as a template; ``next_issue_on`` is when the fee sweep raises the next
draft copy (``recurring_from_id`` points the copy back at its template).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0082_recurring_invoices"
down_revision = "0081_board_digest_sends"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("recurrence", sa.String(12), nullable=True))
    op.add_column("invoices", sa.Column("recur_until", sa.Date(), nullable=True))
    op.add_column("invoices", sa.Column("next_issue_on", sa.Date(), nullable=True))
    op.add_column("invoices", sa.Column("recurring_from_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_invoices_recurring_from_id_invoices", "invoices", "invoices",
        ["recurring_from_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_invoices_next_issue_on", "invoices", ["next_issue_on"])


def downgrade() -> None:
    op.drop_index("ix_invoices_next_issue_on", table_name="invoices")
    op.drop_constraint("fk_invoices_recurring_from_id_invoices", "invoices", type_="foreignkey")
    for column in ("recurring_from_id", "next_issue_on", "recur_until", "recurrence"):
        op.drop_column("invoices", column)
