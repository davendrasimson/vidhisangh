"""Matters: client link, lead counsel, dated team, fee arrangements + milestones,
fee events; counsel rate cards.

Revision ID: 0045_matter_team_fees
Revises: 0044_clients
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0045_matter_team_fees"
down_revision: str | None = "0044_clients"
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
    # ── matters: client link + lead counsel ─────────────────────────
    with op.batch_alter_table("matters") as b:
        b.add_column(sa.Column("client_id", sa.Uuid(as_uuid=True), nullable=True))
        b.add_column(sa.Column("lead_counsel_id", sa.Uuid(as_uuid=True), nullable=True))
        b.create_foreign_key("fk_matters_client", "clients", ["client_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_matters_client_id", "matters", ["client_id"])
    op.create_index("ix_matters_lead_counsel_id", "matters", ["lead_counsel_id"])

    # ── team ────────────────────────────────────────────────────────
    op.create_table(
        "matter_team",
        *_audit_columns(),
        sa.Column("matter_id", sa.Uuid(as_uuid=True), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("role", sa.String(24), nullable=False, server_default="associate"),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("end_reason", sa.String(20), nullable=True),
        sa.Column("successor_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("rate_basis", sa.String(20), nullable=True),
        sa.Column("rate_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("added_by", sa.Uuid(as_uuid=True), nullable=False),
    )
    op.create_index("ix_matter_team_active", "matter_team", ["tenant_id", "user_id", "to_date"])
    _rls("matter_team")

    # ── fee arrangements + milestones ───────────────────────────────
    op.create_table(
        "matter_fee_arrangements",
        *_audit_columns(),
        sa.Column("matter_id", sa.Uuid(as_uuid=True), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("basis", sa.String(16), nullable=False, server_default="fixed"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("fixed_fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("per_hearing_fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("non_effective_hearing_fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("hourly_rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("retainer_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("retainer_period", sa.String(12), nullable=True),
        sa.Column("retainer_includes", sa.String(300), nullable=True),
        sa.Column("fee_cap", sa.Numeric(12, 2), nullable=True),
        sa.Column("expenses_billable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("gst_applicable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("agreed_on", sa.Date(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
    )
    _rls("matter_fee_arrangements")

    op.create_table(
        "matter_fee_milestones",
        *_audit_columns(),
        sa.Column("arrangement_id", sa.Uuid(as_uuid=True), sa.ForeignKey("matter_fee_arrangements.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("matter_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("due_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
    )
    _rls("matter_fee_milestones")

    # ── fee events (what invoices will be raised from) ──────────────
    op.create_table(
        "matter_fee_events",
        *_audit_columns(),
        sa.Column("matter_id", sa.Uuid(as_uuid=True), sa.ForeignKey("matters.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("arrangement_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("milestone_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("hearing_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(10), nullable=False, server_default="unbilled", index=True),
        sa.Column("invoice_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
    )
    _rls("matter_fee_events")

    # ── counsel rate cards ──────────────────────────────────────────
    op.create_table(
        "counsel_rates",
        *_audit_columns(),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("basis", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
    )
    _rls("counsel_rates")


def downgrade() -> None:
    for table in ("counsel_rates", "matter_fee_events", "matter_fee_milestones", "matter_fee_arrangements", "matter_team"):
        op.drop_table(table)
    op.drop_index("ix_matters_lead_counsel_id", table_name="matters")
    op.drop_index("ix_matters_client_id", table_name="matters")
    with op.batch_alter_table("matters") as b:
        b.drop_constraint("fk_matters_client", type_="foreignkey")
        b.drop_column("lead_counsel_id")
        b.drop_column("client_id")
