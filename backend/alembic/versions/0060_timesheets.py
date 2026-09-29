"""Counsel timesheets and invoice linkage.

Revision ID: 0060_timesheets
Revises: 0059_document_esign
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0060_timesheets"
down_revision: str | None = "0059_document_esign"
branch_labels = None
depends_on = None

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' OR "
    "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "time_entries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "matter_id", sa.Uuid(as_uuid=True), sa.ForeignKey("matters.id", ondelete="SET NULL")
        ),
        sa.Column(
            "client_id", sa.Uuid(as_uuid=True), sa.ForeignKey("clients.id", ondelete="SET NULL")
        ),
        sa.Column(
            "invoice_id", sa.Uuid(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="SET NULL")
        ),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "activity_type", sa.String(80), server_default="Professional work", nullable=False
        ),
        sa.Column("billable", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("source", sa.String(20), server_default="manual", nullable=False),
        sa.Column("import_batch", sa.String(40)),
        sa.Column("rejection_reason", sa.String(500)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", sa.Uuid(as_uuid=True)),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 1440", name="time_entry_duration_valid"
        ),
        sa.CheckConstraint("hourly_rate >= 0 AND amount >= 0", name="time_entry_amounts_valid"),
    )
    for name, columns in [
        ("ix_time_entries_tenant_id", ["tenant_id"]),
        ("ix_time_entries_deleted_at", ["deleted_at"]),
        ("ix_time_entries_user_id", ["user_id"]),
        ("ix_time_entries_matter_id", ["matter_id"]),
        ("ix_time_entries_client_id", ["client_id"]),
        ("ix_time_entries_invoice_id", ["invoice_id"]),
        ("ix_time_entries_work_date", ["work_date"]),
        ("ix_time_entries_status", ["status"]),
        ("ix_time_entries_import_batch", ["import_batch"]),
    ]:
        op.create_index(name, "time_entries", columns)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE time_entries ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE time_entries FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON time_entries USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON time_entries")
    op.drop_table("time_entries")
