"""Client portal: tokened access, updates, approvals and shared documents.

Tenant-private practice-management data with the standard ``tenant_isolation``
row-level-security policy.

Revision ID: 0014_portal
Revises: 0013_documents
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_portal"
down_revision: str | None = "0013_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)

TENANT_TABLES = ["portal_accesses", "portal_updates", "portal_approvals", "portal_documents"]


def _tenant_and_timestamps() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "portal_accesses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, nullable=False),
        sa.Column("client_name", sa.String(200), nullable=False),
        sa.Column("client_email", sa.String(320), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", UUID, nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token", name="portal_access_token"),
    )
    op.create_index("ix_portal_accesses_tenant_id", "portal_accesses", ["tenant_id"])
    op.create_index("ix_portal_accesses_matter_id", "portal_accesses", ["matter_id"])
    op.create_index("ix_portal_accesses_token", "portal_accesses", ["token"])

    op.create_table(
        "portal_updates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", UUID, nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_portal_updates_tenant_id", "portal_updates", ["tenant_id"])
    op.create_index("ix_portal_updates_matter_id", "portal_updates", ["matter_id"])

    op.create_table(
        "portal_approvals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("response_note", sa.String(1000), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_portal_approvals_tenant_id", "portal_approvals", ["tenant_id"])
    op.create_index("ix_portal_approvals_matter_id", "portal_approvals", ["matter_id"])
    op.create_index("ix_portal_approvals_status", "portal_approvals", ["status"])

    op.create_table(
        "portal_documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("shared_by", UUID, nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("matter_id", "document_id", name="portal_document_unique"),
    )
    op.create_index("ix_portal_documents_tenant_id", "portal_documents", ["tenant_id"])
    op.create_index("ix_portal_documents_matter_id", "portal_documents", ["matter_id"])
    op.create_index("ix_portal_documents_document_id", "portal_documents", ["document_id"])

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
    op.drop_table("portal_documents")
    op.drop_table("portal_approvals")
    op.drop_table("portal_updates")
    op.drop_table("portal_accesses")
