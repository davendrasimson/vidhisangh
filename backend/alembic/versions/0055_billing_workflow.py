"""Billing documents, follow-ups, receipts, public payment and verification.

Revision ID: 0055_billing_workflow
Revises: 0054_session_devices
"""

from __future__ import annotations

import secrets

import sqlalchemy as sa

from alembic import op

revision: str = "0055_billing_workflow"
down_revision: str | None = "0054_session_devices"
branch_labels = None
depends_on = None

UUID = sa.Uuid(as_uuid=True)
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def _tenant_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("document_type", sa.String(24), nullable=False, server_default="tax_invoice"),
    )
    op.add_column("invoices", sa.Column("verification_code", sa.String(24), nullable=True))
    op.add_column("invoices", sa.Column("payment_token", sa.String(64), nullable=True))
    op.add_column("invoices", sa.Column("source_proforma_id", UUID, nullable=True))
    op.add_column("invoices", sa.Column("converted_invoice_id", UUID, nullable=True))
    op.add_column("invoices", sa.Column("next_follow_up_on", sa.Date(), nullable=True))
    op.add_column(
        "invoices", sa.Column("last_follow_up_at", sa.DateTime(timezone=True), nullable=True)
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM invoices")).fetchall()
    for (invoice_id,) in rows:
        bind.execute(
            sa.text(
                "UPDATE invoices SET verification_code=:code, payment_token=:token WHERE id=:id"
            ),
            {
                "id": invoice_id,
                "code": secrets.token_hex(12).upper(),
                "token": secrets.token_urlsafe(24),
            },
        )
    op.alter_column("invoices", "verification_code", nullable=False)
    op.alter_column("invoices", "payment_token", nullable=False)
    op.create_foreign_key(
        "fk_invoices_source_proforma_id_invoices",
        "invoices",
        "invoices",
        ["source_proforma_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_invoices_converted_invoice_id_invoices",
        "invoices",
        "invoices",
        ["converted_invoice_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_invoices_document_type", "invoices", ["document_type"])
    op.create_index("ix_invoices_verification_code", "invoices", ["verification_code"], unique=True)
    op.create_index("ix_invoices_payment_token", "invoices", ["payment_token"], unique=True)
    op.create_index("ix_invoices_next_follow_up_on", "invoices", ["next_follow_up_on"])

    op.create_table(
        "invoice_follow_ups",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "invoice_id", UUID, sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("channel", sa.String(24), nullable=False, server_default="phone"),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(300), nullable=True),
        sa.Column("next_follow_up_on", sa.Date(), nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        *_tenant_columns(),
    )
    op.create_index("ix_invoice_follow_ups_tenant_id", "invoice_follow_ups", ["tenant_id"])
    op.create_index("ix_invoice_follow_ups_invoice_id", "invoice_follow_ups", ["invoice_id"])
    op.create_index(
        "ix_invoice_follow_ups_next_follow_up_on", "invoice_follow_ups", ["next_follow_up_on"]
    )

    op.create_table(
        "billing_receipts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("receipt_number", sa.String(40), nullable=False),
        sa.Column(
            "invoice_id", UUID, sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "payment_id",
            UUID,
            sa.ForeignKey("payments.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("reference", sa.String(160), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("verification_code", sa.String(24), nullable=False, unique=True),
        sa.Column("created_by", UUID, nullable=False),
        *_tenant_columns(),
        sa.UniqueConstraint("tenant_id", "receipt_number", name="receipt_number_per_tenant"),
    )
    op.create_index("ix_billing_receipts_tenant_id", "billing_receipts", ["tenant_id"])
    op.create_index("ix_billing_receipts_invoice_id", "billing_receipts", ["invoice_id"])
    op.create_index("ix_billing_receipts_received_on", "billing_receipts", ["received_on"])
    op.create_index(
        "ix_billing_receipts_verification_code",
        "billing_receipts",
        ["verification_code"],
        unique=True,
    )

    if bind.dialect.name == "postgresql":
        for table in ("invoice_follow_ups", "billing_receipts"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) "
                f"WITH CHECK ({_PREDICATE})"
            )


def downgrade() -> None:
    op.drop_table("billing_receipts")
    op.drop_table("invoice_follow_ups")
    op.drop_index("ix_invoices_next_follow_up_on", table_name="invoices")
    op.drop_index("ix_invoices_payment_token", table_name="invoices")
    op.drop_index("ix_invoices_verification_code", table_name="invoices")
    op.drop_index("ix_invoices_document_type", table_name="invoices")
    op.drop_constraint("fk_invoices_converted_invoice_id_invoices", "invoices", type_="foreignkey")
    op.drop_constraint("fk_invoices_source_proforma_id_invoices", "invoices", type_="foreignkey")
    for column in (
        "last_follow_up_at",
        "next_follow_up_on",
        "converted_invoice_id",
        "source_proforma_id",
        "payment_token",
        "verification_code",
        "document_type",
    ):
        op.drop_column("invoices", column)
