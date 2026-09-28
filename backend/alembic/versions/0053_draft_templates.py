"""Firm-owned DOCX drafting templates.

Revision ID: 0053_draft_templates
Revises: 0052_audit_purge_guard
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0053_draft_templates"
down_revision: str | None = "0052_audit_purge_guard"
branch_labels = None
depends_on = None

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "draft_templates",
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(80), nullable=False, server_default="Firm templates"),
        sa.Column("language", sa.String(5), nullable=False, server_default="en"),
        sa.Column("source_filename", sa.String(300), nullable=False),
        sa.Column("source_storage_key", sa.String(500), nullable=False),
        sa.Column("source_size", sa.BigInteger(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("content_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("page", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=False),
    )
    op.create_index("ix_draft_templates_tenant_id", "draft_templates", ["tenant_id"])
    op.create_index("ix_draft_templates_deleted_at", "draft_templates", ["deleted_at"])
    op.create_index(
        "ix_draft_templates_tenant_updated", "draft_templates", ["tenant_id", "updated_at"]
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE draft_templates ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE draft_templates FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON draft_templates USING ({_PREDICATE}) "
            f"WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON draft_templates")
    op.drop_table("draft_templates")
