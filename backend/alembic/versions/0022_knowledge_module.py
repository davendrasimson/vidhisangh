"""Knowledge base module: templates, precedents, SOPs & checklists (tenant-scoped).

Revision ID: 0022_knowledge
Revises: 0021_billing
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_knowledge"
down_revision: str | None = "0021_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "knowledge_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("category", sa.String(20), nullable=False, server_default="note"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("practice_area", sa.String(150), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_knowledge_items_tenant_id", "knowledge_items", ["tenant_id"])
    op.create_index("ix_knowledge_items_category", "knowledge_items", ["category"])
    op.create_index("ix_knowledge_items_practice_area", "knowledge_items", ["practice_area"])

    predicate = (
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
    op.execute("ALTER TABLE knowledge_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE knowledge_items FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON knowledge_items "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON knowledge_items")
    op.drop_table("knowledge_items")
