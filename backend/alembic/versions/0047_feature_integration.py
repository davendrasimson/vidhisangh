"""Connect intake, billing, research and marketplace to matters.

Revision ID: 0047_feature_integration
Revises: 0046_document_client
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_feature_integration"
down_revision = "0046_document_client"
branch_labels = None
depends_on = None

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' OR "
    "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def upgrade() -> None:
    with op.batch_alter_table("invoices") as b:
        b.add_column(sa.Column("client_id", sa.Uuid(as_uuid=True), nullable=True))
        b.create_foreign_key("fk_invoices_client", "clients", ["client_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_invoices_client_id", "invoices", ["client_id"])

    with op.batch_alter_table("leads") as b:
        b.add_column(sa.Column("client_id", sa.Uuid(as_uuid=True), nullable=True))
        b.create_foreign_key("fk_leads_client", "clients", ["client_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_leads_client_id", "leads", ["client_id"])

    with op.batch_alter_table("marketplace_listings") as b:
        b.add_column(sa.Column("matter_id", sa.Uuid(as_uuid=True), nullable=True))
        b.add_column(sa.Column("accepted_response_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_marketplace_listings_matter_id", "marketplace_listings", ["matter_id"])

    op.create_table(
        "matter_authorities",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matter_id", sa.Uuid(as_uuid=True), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("judgment_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("act_id", sa.String(80), nullable=True),
        sa.Column("reference", sa.String(300), nullable=False),
        sa.Column("paragraph_no", sa.Integer(), nullable=True),
        sa.Column("quotation", sa.Text(), nullable=True),
        sa.Column("proposition", sa.Text(), nullable=True),
        sa.Column("stance", sa.String(20), nullable=False, server_default="pending_review"),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
    )
    op.create_index("ix_matter_authorities_tenant_id", "matter_authorities", ["tenant_id"])
    op.create_index("ix_matter_authorities_matter_id", "matter_authorities", ["matter_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE matter_authorities ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE matter_authorities FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON matter_authorities USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})")


def downgrade() -> None:
    op.drop_table("matter_authorities")
    op.drop_index("ix_marketplace_listings_matter_id", table_name="marketplace_listings")
    with op.batch_alter_table("marketplace_listings") as b:
        b.drop_column("accepted_response_id")
        b.drop_column("matter_id")
    op.drop_index("ix_leads_client_id", table_name="leads")
    with op.batch_alter_table("leads") as b:
        b.drop_constraint("fk_leads_client", type_="foreignkey")
        b.drop_column("client_id")
    op.drop_index("ix_invoices_client_id", table_name="invoices")
    with op.batch_alter_table("invoices") as b:
        b.drop_constraint("fk_invoices_client", type_="foreignkey")
        b.drop_column("client_id")
