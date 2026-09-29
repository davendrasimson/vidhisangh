"""Document electronic signatures and audit trail.

Revision ID: 0059_document_esign
Revises: 0058_profile_judicial_workspace
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0059_document_esign"
down_revision: str | None = "0058_profile_judicial_workspace"
branch_labels = None
depends_on = None

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' OR "
    "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def _base() -> list[sa.Column]:
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _rls(table: str) -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def upgrade() -> None:
    op.create_table(
        "signature_envelopes",
        *_base(),
        sa.Column(
            "document_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_version_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("document_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("sequential", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("final_storage_key", sa.String(500)),
        sa.Column("final_content_type", sa.String(150)),
        sa.Column("final_checksum", sa.String(64)),
        sa.Column("certificate_storage_key", sa.String(500)),
    )
    op.create_index("ix_signature_envelopes_tenant_id", "signature_envelopes", ["tenant_id"])
    op.create_index("ix_signature_envelopes_document_id", "signature_envelopes", ["document_id"])
    op.create_index("ix_signature_envelopes_status", "signature_envelopes", ["status"])
    op.create_index("ix_signature_envelopes_deleted_at", "signature_envelopes", ["deleted_at"])
    op.create_table(
        "signature_steps",
        *_base(),
        sa.Column(
            "envelope_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("signature_envelopes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("signer_kind", sa.String(20), nullable=False),
        sa.Column("signer_user_id", sa.Uuid(as_uuid=True)),
        sa.Column("signer_name", sa.String(200), nullable=False),
        sa.Column("signer_email", sa.String(1024), nullable=False),
        sa.Column("designation", sa.String(200)),
        sa.Column("status", sa.String(20), nullable=False, server_default="waiting"),
        sa.Column("token_hash", sa.String(64), unique=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("otp_hash", sa.String(64)),
        sa.Column("otp_expires_at", sa.DateTime(timezone=True)),
        sa.Column("otp_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("session_hash", sa.String(64)),
        sa.Column("session_expires_at", sa.DateTime(timezone=True)),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("signed_name", sa.String(200)),
        sa.Column("signature_data", sa.String(800000)),
        sa.Column("consent_text", sa.Text()),
        sa.Column("remarks", sa.Text()),
        sa.Column("ip_address", sa.String(512)),
        sa.Column("user_agent", sa.String(2000)),
        sa.UniqueConstraint("envelope_id", "step_order", name="signature_step_order_unique"),
    )
    for name, cols in [
        ("ix_signature_steps_tenant_id", ["tenant_id"]),
        ("ix_signature_steps_envelope_id", ["envelope_id"]),
        ("ix_signature_steps_signer_user_id", ["signer_user_id"]),
        ("ix_signature_steps_status", ["status"]),
        ("ix_signature_steps_deleted_at", ["deleted_at"]),
    ]:
        op.create_index(name, "signature_steps", cols)
    op.create_table(
        "signature_events",
        *_base(),
        sa.Column(
            "envelope_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("signature_envelopes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.Uuid(as_uuid=True)),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True)),
        sa.Column("actor_label", sa.String(200)),
        sa.Column("ip_address", sa.String(512)),
        sa.Column("detail", sa.JSON(), nullable=False, server_default="{}"),
    )
    for name, cols in [
        ("ix_signature_events_tenant_id", ["tenant_id"]),
        ("ix_signature_events_envelope_id", ["envelope_id"]),
        ("ix_signature_events_event_type", ["event_type"]),
        ("ix_signature_events_deleted_at", ["deleted_at"]),
    ]:
        op.create_index(name, "signature_events", cols)
    for table in ("signature_envelopes", "signature_steps", "signature_events"):
        _rls(table)


def downgrade() -> None:
    for table in ("signature_events", "signature_steps", "signature_envelopes"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.drop_table(table)
