"""Authentication hardening (security audit 2026-09: A-1/2/7/9/11/14/18/19/21/23/24/26).

- users: password_must_change, token_epoch, email verification token,
  pending MFA secret.
- portal_accesses / client_kyc_requests: tokens stored as peppered hashes
  (existing rows hashed in place, clear-text nulled), portal links expire.
- oauth_identities: (provider, subject) links for SSO.
- password_reset_tokens: single-use hashed reset / invitation tokens.

Revision ID: 0050_auth_hardening
Revises: 0049_privacy
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision: str = "0050_auth_hardening"
down_revision: str | None = "0049_privacy"
branch_labels = None
depends_on = None


def _global_audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _hash_existing_tokens(table: str) -> None:
    """Replace clear-text link tokens with their peppered hash (same pepper the
    application uses, so links already sent keep working)."""
    from app.core.security import hash_link_token

    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, token FROM {table} WHERE token IS NOT NULL")).fetchall()
    for row_id, token in rows:
        bind.execute(
            sa.text(f"UPDATE {table} SET token_hash = :h, token = NULL WHERE id = :id"),
            {"h": hash_link_token(token), "id": row_id},
        )


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("mfa_pending_secret", sa.String(255), nullable=True))
        b.add_column(sa.Column("password_must_change", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("token_epoch", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("email_verification_token_hash", sa.String(64), nullable=True))
        b.add_column(sa.Column("email_verification_expires_at", sa.DateTime(timezone=True), nullable=True))

    # ── portal_accesses: hashed, expiring tokens ──────────────────
    with op.batch_alter_table("portal_accesses") as b:
        b.alter_column("token", existing_type=sa.String(64), nullable=True)
        b.add_column(sa.Column("token_hash", sa.String(64), nullable=True))
        b.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_portal_accesses_token_hash", "portal_accesses", ["token_hash"], unique=True)
    _hash_existing_tokens("portal_accesses")
    # Links issued before expiry existed get the full default lifetime from now.
    from app.core.config import settings

    op.get_bind().execute(
        sa.text("UPDATE portal_accesses SET expires_at = :exp WHERE expires_at IS NULL"),
        {"exp": datetime.now(UTC) + timedelta(days=settings.PORTAL_ACCESS_EXPIRE_DAYS)},
    )

    # ── client_kyc_requests: hashed tokens ────────────────────────
    with op.batch_alter_table("client_kyc_requests") as b:
        b.alter_column("token", existing_type=sa.String(64), nullable=True)
        b.add_column(sa.Column("token_hash", sa.String(64), nullable=True))
    op.create_index("ix_client_kyc_requests_token_hash", "client_kyc_requests", ["token_hash"], unique=True)
    _hash_existing_tokens("client_kyc_requests")

    # ── oauth_identities (global, like oauth_states) ──────────────
    op.create_table(
        "oauth_identities",
        *_global_audit_columns(),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "subject", name="uq_oauth_identity_provider_subject"),
    )
    op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"])
    op.create_index("ix_oauth_identities_deleted_at", "oauth_identities", ["deleted_at"])

    # ── password_reset_tokens (global — the flow starts pre-tenant) ─
    op.create_table(
        "password_reset_tokens",
        *_global_audit_columns(),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(12), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)
    op.create_index("ix_password_reset_tokens_deleted_at", "password_reset_tokens", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("oauth_identities")
    op.drop_index("ix_client_kyc_requests_token_hash", table_name="client_kyc_requests")
    with op.batch_alter_table("client_kyc_requests") as b:
        b.drop_column("token_hash")
        # Clear-text tokens cannot be recovered from hashes; the column stays nullable.
    op.drop_index("ix_portal_accesses_token_hash", table_name="portal_accesses")
    with op.batch_alter_table("portal_accesses") as b:
        b.drop_column("last_accessed_at")
        b.drop_column("expires_at")
        b.drop_column("token_hash")
    with op.batch_alter_table("users") as b:
        b.drop_column("email_verification_expires_at")
        b.drop_column("email_verification_token_hash")
        b.drop_column("token_epoch")
        b.drop_column("password_must_change")
        b.drop_column("mfa_pending_secret")
