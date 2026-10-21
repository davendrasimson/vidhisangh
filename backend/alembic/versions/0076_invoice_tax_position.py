"""Invoices keep the client's tax position as issued: GSTIN, treatment, place of
supply, our state (CGST+SGST or IGST), reverse charge and TDS.

Revision ID: 0076_invoice_tax_position
Revises: 0075_group_post_rich
"""

import sqlalchemy as sa

from alembic import op

revision = "0076_invoice_tax_position"
down_revision = "0075_group_post_rich"
branch_labels = None
depends_on = None

_COLUMNS = ("client_gstin", "gst_treatment", "place_of_supply_code", "supplier_state_code",
            "reverse_charge", "tds_section", "tds_rate")


def upgrade() -> None:
    op.add_column("invoices", sa.Column("client_gstin", sa.String(255), nullable=True))  # encrypted
    op.add_column("invoices", sa.Column("gst_treatment", sa.String(30), nullable=True))
    op.add_column("invoices", sa.Column("place_of_supply_code", sa.String(2), nullable=True))
    op.add_column("invoices", sa.Column("supplier_state_code", sa.String(2), nullable=True))
    op.add_column("invoices", sa.Column("reverse_charge", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("invoices", sa.Column("tds_section", sa.String(10), nullable=True))
    op.add_column("invoices", sa.Column("tds_rate", sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.drop_column("invoices", column)
