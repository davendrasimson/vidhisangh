"""Initial core schema: tenancy, identity, RBAC + row-level security.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

# Tenant-scoped tables that get an RLS isolation policy.
TENANT_TABLES = ["users", "refresh_tokens", "mfa_backup_codes", "trusted_devices"]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    # pgvector is only required for Phase 4 (semantic search / RAG). Create it if
    # available, but do not fail the migration on installations without it.
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS vector;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'pgvector not installed; skipping (needed for Phase 4).';
        END
        $$;
        """
    )

    # ── tenants (global) ────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("type", sa.String(32), nullable=False, server_default="individual"),
        sa.Column("status", sa.String(32), nullable=False, server_default="trial"),
        sa.Column("plan", sa.String(32), nullable=False, server_default="free"),
        sa.Column("region", sa.String(32), nullable=False, server_default="ap-south-1"),
        sa.Column("primary_contact_email", sa.String(320), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        *_timestamps(),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_index("ix_tenants_status", "tenants", ["status"])

    # ── permissions (global catalog) ────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(400), nullable=True),
        sa.Column("module", sa.String(60), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_index("ix_permissions_module", "permissions", ["module"])

    # ── roles (system + tenant-custom) ──────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID, nullable=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(400), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE",
            name="fk_roles_tenant_id_tenants",
        ),
        sa.UniqueConstraint("tenant_id", "code", name="roles_tenant_code"),
    )
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])
    op.create_index("ix_roles_code", "roles", ["code"])

    # ── role_permissions (assoc) ────────────────────────────────────
    op.create_table(
        "role_permissions",
        sa.Column("role_id", UUID, nullable=False),
        sa.Column("permission_id", UUID, nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permissions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    # ── users (tenant-scoped) ───────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "is_email_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mfa_secret", sa.String(255), nullable=True),
        sa.Column(
            "failed_login_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE",
            name="fk_users_tenant_id_tenants",
        ),
        sa.UniqueConstraint("tenant_id", "email", name="users_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_phone", "users", ["phone"])
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])

    # ── user_roles (assoc) ──────────────────────────────────────────
    op.create_table(
        "user_roles",
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("role_id", UUID, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    # ── refresh_tokens (tenant-scoped) ──────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", UUID, nullable=True),
        sa.Column("device_label", sa.String(200), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(400), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE",
            name="fk_refresh_tokens_tenant_id_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_refresh_tokens_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"], ["refresh_tokens.id"], ondelete="SET NULL",
            name="fk_refresh_tokens_replaced_by_id_refresh_tokens",
        ),
    )
    op.create_index("ix_refresh_tokens_tenant_id", "refresh_tokens", ["tenant_id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])

    # ── mfa_backup_codes (tenant-scoped) ────────────────────────────
    op.create_table(
        "mfa_backup_codes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE",
            name="fk_mfa_backup_codes_tenant_id_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_mfa_backup_codes_user_id_users",
        ),
    )
    op.create_index("ix_mfa_backup_codes_tenant_id", "mfa_backup_codes", ["tenant_id"])
    op.create_index("ix_mfa_backup_codes_user_id", "mfa_backup_codes", ["user_id"])

    # ── trusted_devices (tenant-scoped) ─────────────────────────────
    op.create_table(
        "trusted_devices",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("device_fingerprint", sa.String(128), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trusted_until", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE",
            name="fk_trusted_devices_tenant_id_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_trusted_devices_user_id_users",
        ),
    )
    op.create_index("ix_trusted_devices_tenant_id", "trusted_devices", ["tenant_id"])
    op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])
    op.create_index(
        "ix_trusted_devices_fingerprint", "trusted_devices", ["device_fingerprint"]
    )

    _apply_row_level_security()


def _apply_row_level_security() -> None:
    """Enforce tenant isolation in the database itself.

    A row is visible only when the ``app.current_tenant`` session variable
    matches its ``tenant_id`` — unless ``app.bypass_rls`` is 'on' (auth flows &
    migrations). FORCE makes the policy apply even to the table owner.
    """
    tenant_predicate = (
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({tenant_predicate}) WITH CHECK ({tenant_predicate})"
        )

    # Roles: system roles (tenant_id IS NULL) are visible to everyone.
    role_predicate = (
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR tenant_id IS NULL "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
    op.execute("ALTER TABLE roles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE roles FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON roles "
        f"USING ({role_predicate}) WITH CHECK ({role_predicate})"
    )


def downgrade() -> None:
    for table in [*TENANT_TABLES, "roles"]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("trusted_devices")
    op.drop_table("mfa_backup_codes")
    op.drop_table("refresh_tokens")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.drop_table("tenants")
