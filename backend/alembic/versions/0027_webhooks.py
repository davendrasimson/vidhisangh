"""Outbound webhooks: endpoints + delivery log (tenant-scoped + RLS).

Revision ID: 0027_webhooks
Revises: 0026_audit_events
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_webhooks"
down_revision: str | None = "0026_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _enable_rls(table: str) -> None:
    predicate = (
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("secret", sa.String(80), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_webhook_endpoints_tenant_id", "webhook_endpoints", ["tenant_id"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("endpoint_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("tenant_id", UUID, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["endpoint_id"], ["webhook_endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_webhook_deliveries_tenant_id", "webhook_deliveries", ["tenant_id"])
    op.create_index("ix_webhook_deliveries_endpoint_id", "webhook_deliveries", ["endpoint_id"])
    op.create_index("ix_webhook_deliveries_event_type", "webhook_deliveries", ["event_type"])

    _enable_rls("webhook_endpoints")
    _enable_rls("webhook_deliveries")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON webhook_deliveries")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON webhook_endpoints")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
