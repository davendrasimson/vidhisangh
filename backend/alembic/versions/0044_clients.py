"""Client master: clients (individual/business, tax config, consent) and KYC requests.

Revision ID: 0044_clients
Revises: 0043_drafting
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0044_clients"
down_revision: str | None = "0043_drafting"
branch_labels = None
depends_on = None

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})")


def upgrade() -> None:
    op.create_table(
        "clients",
        *_audit_columns(),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("client_code", sa.String(30), nullable=True),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("first_name", sa.String(120), nullable=True),
        sa.Column("last_name", sa.String(120), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("father_or_spouse_name", sa.String(200), nullable=True),
        sa.Column("occupation", sa.String(120), nullable=True),
        sa.Column("legal_name", sa.String(300), nullable=True),
        sa.Column("trade_name", sa.String(300), nullable=True),
        sa.Column("business_type", sa.String(40), nullable=True),
        sa.Column("cin", sa.String(21), nullable=True),
        sa.Column("incorporation_date", sa.Date(), nullable=True),
        sa.Column("contact_person_name", sa.String(200), nullable=True),
        sa.Column("contact_person_designation", sa.String(120), nullable=True),
        sa.Column("contact_person_email", sa.String(254), nullable=True),
        sa.Column("contact_person_mobile", sa.String(20), nullable=True),
        sa.Column("pan", sa.String(10), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("mobile", sa.String(20), nullable=True),
        sa.Column("address_line1", sa.String(300), nullable=True),
        sa.Column("address_line2", sa.String(300), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("state", sa.String(120), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=True),
        sa.Column("pincode", sa.String(10), nullable=True),
        sa.Column("country", sa.String(60), nullable=False, server_default="India"),
        sa.Column("consent_email", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consent_mobile", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consent_whatsapp", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_source", sa.String(40), nullable=True),
        sa.Column("gst_applicable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("gst_treatment", sa.String(24), nullable=False, server_default="unregistered"),
        sa.Column("reverse_charge", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("place_of_supply_code", sa.String(2), nullable=True),
        sa.Column("tds_applicable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tds_section", sa.String(10), nullable=True),
        sa.Column("tds_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("tan", sa.String(10), nullable=True),
        sa.Column("msme_udyam", sa.String(25), nullable=True),
        sa.Column("kyc_status", sa.String(12), nullable=False, server_default="not_started"),
        sa.Column("kyc_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kyc_verified_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=False),
    )
    op.create_index("ix_clients_tenant_name", "clients", ["tenant_id", "display_name"])
    op.create_index("ix_clients_tenant_kind", "clients", ["tenant_id", "kind"])
    _rls("clients")

    op.create_table(
        "client_kyc_requests",
        *_audit_columns(),
        sa.Column("client_id", sa.Uuid(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="sent"),
        sa.Column("sent_to_email", sa.String(254), nullable=True),
        sa.Column("sent_to_mobile", sa.String(20), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prefill", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("submitted_data", sa.JSON(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_ip", sa.String(64), nullable=True),
        sa.Column("issues", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("initiated_by", sa.Uuid(as_uuid=True), nullable=False),
    )
    _rls("client_kyc_requests")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON client_kyc_requests")
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON clients")
    op.drop_table("client_kyc_requests")
    op.drop_index("ix_clients_tenant_kind", table_name="clients")
    op.drop_index("ix_clients_tenant_name", table_name="clients")
    op.drop_table("clients")
