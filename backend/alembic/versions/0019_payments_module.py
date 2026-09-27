"""Payments module: Razorpay-backed payment records (tenant-scoped).

Revision ID: 0019_payments
Revises: 0018_news
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_payments"
down_revision: str | None = "0018_news"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_order_id", sa.String(80), nullable=False),
        sa.Column("provider_payment_id", sa.String(80), nullable=True),
        sa.Column("receipt", sa.String(120), nullable=True),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("matter_id", UUID, nullable=True),
        sa.Column("invoice_id", UUID, nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_provider_order_id", "payments", ["provider_order_id"])
    op.create_index("ix_payments_provider_payment_id", "payments", ["provider_payment_id"])
    op.create_index("ix_payments_matter_id", "payments", ["matter_id"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])

    predicate = (
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
    op.execute("ALTER TABLE payments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE payments FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON payments USING ({predicate}) WITH CHECK ({predicate})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON payments")
    op.drop_table("payments")
