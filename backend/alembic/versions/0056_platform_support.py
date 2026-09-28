"""Platform support desk, grievance messages and moderation audit.

Revision ID: 0056_platform_support
Revises: 0055_billing_workflow
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0056_platform_support"
down_revision: str | None = "0055_billing_workflow"
branch_labels = None
depends_on = None

UUID = sa.Uuid(as_uuid=True)
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        *_audit_columns(),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("ticket_number", sa.String(32), nullable=False, unique=True),
        sa.Column(
            "requester_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("requester_name", sa.String(200), nullable=False),
        sa.Column("requester_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("page_url", sa.String(1000), nullable=True),
        sa.Column("browser_context", sa.String(500), nullable=True),
        sa.Column("assigned_to_id", UUID, nullable=True),
        sa.Column("assigned_to_name", sa.String(200), nullable=True),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in (
        "tenant_id",
        "ticket_number",
        "requester_id",
        "category",
        "priority",
        "status",
        "deleted_at",
    ):
        op.create_index(f"ix_support_tickets_{column}", "support_tickets", [column])

    op.create_table(
        "support_ticket_messages",
        *_audit_columns(),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "ticket_id",
            UUID,
            sa.ForeignKey("support_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_id", UUID, nullable=False),
        sa.Column("author_name", sa.String(200), nullable=False),
        sa.Column("is_staff", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("body", sa.Text(), nullable=False),
    )
    for column in ("tenant_id", "ticket_id", "author_id", "deleted_at"):
        op.create_index(f"ix_support_ticket_messages_{column}", "support_ticket_messages", [column])

    op.create_table(
        "platform_admin_actions",
        *_audit_columns(),
        sa.Column("actor_id", UUID, nullable=False),
        sa.Column("actor_email", sa.String(320), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
    )
    for column in ("actor_id", "action", "entity_type", "entity_id", "deleted_at"):
        op.create_index(f"ix_platform_admin_actions_{column}", "platform_admin_actions", [column])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("support_tickets", "support_ticket_messages"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) "
                f"WITH CHECK ({_PREDICATE})"
            )


def downgrade() -> None:
    op.drop_table("platform_admin_actions")
    op.drop_table("support_ticket_messages")
    op.drop_table("support_tickets")
