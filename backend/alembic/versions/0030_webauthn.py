"""Passkeys/WebAuthn: credentials (tenant-scoped + RLS) + challenges (global).

Revision ID: 0030_webauthn
Revises: 0029_api_keys
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_webauthn"
down_revision: str | None = "0029_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "webauthn_credentials",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("credential_id", sa.String(255), nullable=False),
        sa.Column("public_key", sa.String(1024), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("transports", sa.JSON(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", UUID, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("credential_id", name="uq_webauthn_credential_id"),
    )
    op.create_index("ix_webauthn_credentials_tenant_id", "webauthn_credentials", ["tenant_id"])
    op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"])
    op.create_index("ix_webauthn_credentials_credential_id", "webauthn_credentials", ["credential_id"])

    predicate = (
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
    op.execute("ALTER TABLE webauthn_credentials ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE webauthn_credentials FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON webauthn_credentials "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )

    op.create_table(
        "webauthn_challenges",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("challenge", sa.String(128), nullable=False),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.UniqueConstraint("challenge", name="uq_webauthn_challenge"),
    )
    op.create_index("ix_webauthn_challenges_challenge", "webauthn_challenges", ["challenge"])


def downgrade() -> None:
    op.drop_table("webauthn_challenges")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON webauthn_credentials")
    op.drop_table("webauthn_credentials")
