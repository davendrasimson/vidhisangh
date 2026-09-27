"""CRM module: leads and lead activities (tenant-scoped).

Revision ID: 0020_crm
Revises: 0019_payments
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_crm"
down_revision: str | None = "0019_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)

TENANT_TABLES = ["leads", "lead_activities"]


def _tenant_and_timestamps() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="other"),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("practice_area", sa.String(150), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("estimated_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("referred_by", sa.String(200), nullable=True),
        sa.Column("assigned_to", UUID, nullable=True),
        sa.Column("converted_matter_id", UUID, nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_leads_tenant_id", "leads", ["tenant_id"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_source", "leads", ["source"])
    op.create_index("ix_leads_assigned_to", "leads", ["assigned_to"])

    op.create_table(
        "lead_activities",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("lead_id", UUID, nullable=False),
        sa.Column("type", sa.String(20), nullable=False, server_default="note"),
        sa.Column("subject", sa.String(300), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_lead_activities_tenant_id", "lead_activities", ["tenant_id"])
    op.create_index("ix_lead_activities_lead_id", "lead_activities", ["lead_id"])
    op.create_index("ix_lead_activities_due_on", "lead_activities", ["due_on"])

    predicate = (
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("lead_activities")
    op.drop_table("leads")
