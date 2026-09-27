"""Feature flags: per-tenant capability overrides (tenant-scoped + RLS).

Revision ID: 0025_feature_flags
Revises: 0024_notif_channels
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_feature_flags"
down_revision: str | None = "0024_notif_channels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_feature_flag_tenant_key"),
    )
    op.create_index("ix_feature_flags_tenant_id", "feature_flags", ["tenant_id"])
    op.create_index("ix_feature_flags_key", "feature_flags", ["key"])

    predicate = (
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
    op.execute("ALTER TABLE feature_flags ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE feature_flags FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON feature_flags "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON feature_flags")
    op.drop_table("feature_flags")
