"""Documents module: folders, documents and version history.

Tenant-private document management. Bytes live in object storage; these tables
hold metadata + versions. Every table is tenant-scoped with the same
``tenant_isolation`` row-level-security policy as the rest of the schema.

Revision ID: 0013_documents
Revises: 0012_matters
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_documents"
down_revision: str | None = "0012_matters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)

TENANT_TABLES = ["document_folders", "documents", "document_versions"]


def _tenant_and_timestamps() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "document_folders",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("parent_id", UUID, nullable=True),
        sa.Column("matter_id", UUID, nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["document_folders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_document_folders_tenant_id", "document_folders", ["tenant_id"])
    op.create_index("ix_document_folders_parent_id", "document_folders", ["parent_id"])
    op.create_index("ix_document_folders_matter_id", "document_folders", ["matter_id"])

    op.create_table(
        "documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("folder_id", UUID, nullable=True),
        sa.Column("matter_id", UUID, nullable=True),
        sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("current_version_id", UUID, nullable=True),
        sa.Column("version_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_by", UUID, nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", UUID, nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folder_id"], ["document_folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_folder_id", "documents", ["folder_id"])
    op.create_index("ix_documents_matter_id", "documents", ["matter_id"])

    op.create_table(
        "document_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column("uploaded_by", UUID, nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_document_versions_tenant_id", "document_versions", ["tenant_id"])
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])

    _apply_rls()


def _apply_rls() -> None:
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
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("document_folders")
