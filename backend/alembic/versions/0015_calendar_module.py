"""Calendar module: standalone calendar events (tenant-scoped).

The agenda merges these with matter hearings and task deadlines at query time —
no extra tables needed for those.

Revision ID: 0015_calendar
Revises: 0014_portal
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_calendar"
down_revision: str | None = "0014_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(20), nullable=False, server_default="meeting"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("matter_id", UUID, nullable=True),
        sa.Column("assigned_to", UUID, nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_calendar_events_tenant_id", "calendar_events", ["tenant_id"])
    op.create_index("ix_calendar_events_start_at", "calendar_events", ["start_at"])
    op.create_index("ix_calendar_events_matter_id", "calendar_events", ["matter_id"])

    predicate = (
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
    op.execute("ALTER TABLE calendar_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE calendar_events FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON calendar_events "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON calendar_events")
    op.drop_table("calendar_events")
