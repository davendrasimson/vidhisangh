"""Matters module: matters, parties, hearings, tasks, notes.

Tenant-private practice-management data — every table is tenant-scoped and gets
the same ``tenant_isolation`` row-level-security policy as the core schema.

Revision ID: 0012_matters
Revises: 0011_notifications
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_matters"
down_revision: str | None = "0011_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)

TENANT_TABLES = ["matters", "matter_parties", "hearings", "matter_tasks", "matter_notes"]


def _tenant_and_timestamps() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "matters",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_number", sa.String(40), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("client_name", sa.String(200), nullable=False),
        sa.Column("matter_type", sa.String(20), nullable=False, server_default="litigation"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("stage", sa.String(20), nullable=False, server_default="intake"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("practice_area", sa.String(150), nullable=True),
        sa.Column("court", sa.String(200), nullable=True),
        sa.Column("case_number", sa.String(120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("opened_on", sa.Date(), nullable=True),
        sa.Column("assigned_to", UUID, nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "matter_number", name="matter_number_per_tenant"),
    )
    op.create_index("ix_matters_tenant_id", "matters", ["tenant_id"])
    op.create_index("ix_matters_status", "matters", ["status"])
    op.create_index("ix_matters_matter_type", "matters", ["matter_type"])
    op.create_index("ix_matters_assigned_to", "matters", ["assigned_to"])

    op.create_table(
        "matter_parties",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(80), nullable=False),
        sa.Column("contact", sa.String(200), nullable=True),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_matter_parties_tenant_id", "matter_parties", ["tenant_id"])
    op.create_index("ix_matter_parties_matter_id", "matter_parties", ["matter_id"])

    op.create_table(
        "hearings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, nullable=False),
        sa.Column("scheduled_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("court", sa.String(200), nullable=True),
        sa.Column("judge", sa.String(200), nullable=True),
        sa.Column("purpose", sa.String(300), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("next_date", sa.DateTime(timezone=True), nullable=True),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_hearings_tenant_id", "hearings", ["tenant_id"])
    op.create_index("ix_hearings_matter_id", "hearings", ["matter_id"])
    op.create_index("ix_hearings_scheduled_on", "hearings", ["scheduled_on"])

    op.create_table(
        "matter_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("assigned_to", UUID, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_matter_tasks_tenant_id", "matter_tasks", ["tenant_id"])
    op.create_index("ix_matter_tasks_matter_id", "matter_tasks", ["matter_id"])
    op.create_index("ix_matter_tasks_due_on", "matter_tasks", ["due_on"])
    op.create_index("ix_matter_tasks_status", "matter_tasks", ["status"])

    op.create_table(
        "matter_notes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, nullable=False),
        sa.Column("author_id", UUID, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        *_tenant_and_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_matter_notes_tenant_id", "matter_notes", ["tenant_id"])
    op.create_index("ix_matter_notes_matter_id", "matter_notes", ["matter_id"])

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
    op.drop_table("matter_notes")
    op.drop_table("matter_tasks")
    op.drop_table("hearings")
    op.drop_table("matter_parties")
    op.drop_table("matters")
