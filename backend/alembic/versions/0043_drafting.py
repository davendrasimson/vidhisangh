"""Drafting: authored documents (the in-app editor) and their versions.

Revision ID: 0043_drafting
Revises: 0042_news_images

Two tenant-scoped tables with the standard RLS policy. ``drafts.content_json``
is the editor's ProseMirror document — the source of truth from which the
HTML and the DOCX export are derived.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0043_drafting"
down_revision: str | None = "0042_news_images"
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
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )


def upgrade() -> None:
    op.create_table(
        "drafts",
        *_audit_columns(),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("language", sa.String(5), nullable=False, server_default="en"),
        sa.Column("template_id", sa.String(80), nullable=True),
        sa.Column(
            "matter_id", sa.Uuid(as_uuid=True), sa.ForeignKey("matters.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("content_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("content_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("page", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "library_document_id", sa.Uuid(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=False),
    )
    op.create_index("ix_drafts_tenant_updated", "drafts", ["tenant_id", "updated_at"])
    _rls("drafts")

    op.create_table(
        "draft_versions",
        *_audit_columns(),
        sa.Column(
            "draft_id", sa.Uuid(as_uuid=True), sa.ForeignKey("drafts.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("content_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("content_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.UniqueConstraint("draft_id", "version_no", name="uq_draft_versions_no"),
    )
    _rls("draft_versions")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON draft_versions")
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON drafts")
    op.drop_table("draft_versions")
    op.drop_index("ix_drafts_tenant_updated", table_name="drafts")
    op.drop_table("drafts")
