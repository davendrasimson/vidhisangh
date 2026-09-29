"""Tenant-configurable matter sections, fields and values.

Revision ID: 0061_matter_custom_fields
Revises: 0060_timesheets
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0061_matter_custom_fields"
down_revision: str | None = "0060_timesheets"
branch_labels = None
depends_on = None

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' OR "
    "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def _base_columns() -> list[sa.Column]:
    return [
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
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    ]


def _secure(table: str) -> None:
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    op.create_index(f"ix_{table}_deleted_at", table, ["deleted_at"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def upgrade() -> None:
    op.create_table(
        "matter_custom_sections",
        *_base_columns(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(400)),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="matter_custom_section_name_per_tenant"),
    )
    _secure("matter_custom_sections")

    op.create_table(
        "matter_custom_fields",
        *_base_columns(),
        sa.Column("section_key", sa.String(40), server_default="additional", nullable=False),
        sa.Column(
            "custom_section_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("matter_custom_sections.id", ondelete="SET NULL"),
        ),
        sa.Column("field_key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("help_text", sa.String(400)),
        sa.Column("field_type", sa.String(24), nullable=False),
        sa.Column("options", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_encrypted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_masked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_reportable", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "field_key", name="matter_custom_field_key_per_tenant"),
    )
    _secure("matter_custom_fields")
    op.create_index(
        "ix_matter_custom_fields_custom_section_id", "matter_custom_fields", ["custom_section_id"]
    )

    op.create_table(
        "matter_custom_values",
        *_base_columns(),
        sa.Column(
            "matter_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("matters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "field_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("matter_custom_fields.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plain_value", sa.Text()),
        sa.Column("encrypted_value", sa.String(16384)),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.UniqueConstraint("matter_id", "field_id", name="matter_custom_value_per_field"),
    )
    _secure("matter_custom_values")
    op.create_index("ix_matter_custom_values_matter_id", "matter_custom_values", ["matter_id"])
    op.create_index("ix_matter_custom_values_field_id", "matter_custom_values", ["field_id"])


def downgrade() -> None:
    for table in ("matter_custom_values", "matter_custom_fields", "matter_custom_sections"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.drop_table(table)
