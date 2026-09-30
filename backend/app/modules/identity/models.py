"""Identity & access-management domain models.

Covers users, the RBAC model (permissions → roles → users), rotating refresh
tokens, MFA (TOTP) with backup codes, and trusted-device management.

RBAC design:
- ``Permission`` — a global catalog of fine-grained capabilities
  (``module:action`` codes, e.g. ``matter:create``). System-defined.
- ``Role`` — a named bundle of permissions. System roles (``tenant_id IS NULL``)
  ship with the platform; tenants may also define custom roles.
- Users are granted roles; a user's effective permissions are the union across
  their roles plus any direct grants.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.db.base_class import AuditedBase, Base, TenantScopedBase

# ─── Association tables ─────────────────────────────────────────────
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        Uuid(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class MfaMethodType(StrEnum):
    TOTP = "totp"
    WEBAUTHN = "webauthn"
    SMS = "sms"


# ─── Permission catalog (global) ────────────────────────────────────
class Permission(AuditedBase):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(400), nullable=True)
    module: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    roles: Mapped[list["Role"]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )


# ─── Roles (system + tenant-custom) ─────────────────────────────────
class Role(AuditedBase):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="roles_tenant_code"),)

    # Null tenant_id => a built-in system role shared across all tenants.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(400), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )
    users: Mapped[list["User"]] = relationship(
        secondary=user_roles, back_populates="roles"
    )


# ─── User ───────────────────────────────────────────────────────────
class User(TenantScopedBase):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="users_tenant_email"),
        Index("users_verified_phone_unique", "phone", unique=True,
              postgresql_where=text("deleted_at IS NULL AND is_phone_verified = true"),
              sqlite_where=text("deleted_at IS NULL AND is_phone_verified = 1")),
        # An email address identifies exactly ONE account platform-wide, so
        # sign-in never has to ask which organisation was meant. Partial —
        # matching the `deleted_at IS NULL` filter every lookup applies — so a
        # soft-deleted account does not hold its address against the platform.
        # (`users_tenant_email` above is not partial, so the tenant that
        # soft-deleted a user still cannot re-add that address itself.)
        Index(
            "users_email_global_unique",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    is_phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verification_delivery_token: Mapped[str | None] = mapped_column(
        EncryptedString(512), nullable=True
    )
    email_verification_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    email_verification_next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # MFA. ``mfa_pending_secret`` holds a secret being enrolled; it only becomes
    # ``mfa_secret`` once the user proves possession with a valid code, so a
    # re-enrolment never breaks the authenticator that is currently in use.
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)
    mfa_pending_secret: Mapped[str | None] = mapped_column(EncryptedString(255), nullable=True)

    # Brute-force protection / account lockout
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    posting_restricted_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    network_profile_removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── DPDP s.5/s.6 (privacy agent): which Terms/Privacy Notice version the
    # user accepted at sign-up, and when. Compared with CURRENT_TERMS_VERSION
    # so the SPA can re-prompt after a change.
    terms_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Admin-issued temporary credential: until changed, tokens are scoped to
    # /auth/change-password (claim ``pmc``).
    password_must_change: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=text("false")
    )
    # Bumped on every revocation event (role change, deactivation, password
    # change/reset, revoke-all); access tokens carry it as ``ep`` and are
    # denied when older than the Redis denylist entry (immediate revocation).
    token_epoch: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default=text("0")
    )
    # Single-use verification; new email registrations must verify before sign-in.
    email_verification_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    roles: Mapped[list[Role]] = relationship(
        secondary=user_roles, back_populates="users", lazy="selectin"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    backup_codes: Mapped[list["MfaBackupCode"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def permission_codes(self) -> set[str]:
        """Effective permissions across all assigned roles."""
        codes: set[str] = set()
        for role in self.roles:
            codes.update(perm.code for perm in role.permissions)
        return codes


# ─── Rotating refresh tokens ────────────────────────────────────────
class RefreshToken(TenantScopedBase):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Rotation lineage — detects refresh-token reuse (theft) attacks.
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    device_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Random, non-secret identifier generated by the app and retained in this
    # browser. It lets a new sign-in replace this browser's older refresh-token
    # family without merging unrelated devices that happen to share a user agent.
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    @property
    def is_active(self) -> bool:
        from datetime import UTC, datetime as _dt

        expires = (
            self.expires_at
            if self.expires_at.tzinfo is not None
            else self.expires_at.replace(tzinfo=UTC)
        )
        return self.revoked_at is None and expires > _dt.now(UTC)


# ─── MFA backup codes ───────────────────────────────────────────────
class MfaBackupCode(TenantScopedBase):
    __tablename__ = "mfa_backup_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="backup_codes")


# ─── Trusted devices (device management) ────────────────────────────
class TrustedDevice(TenantScopedBase):
    __tablename__ = "trusted_devices"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    device_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trusted_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ─── OAuth / OIDC sign-in state (global, pre-authentication) ─────────
class OAuthState(AuditedBase):
    """Short-lived CSRF/PKCE state persisted between the authorize redirect and
    the callback. Global (no tenant) — the tenant is only known once the user
    identity is resolved on callback."""

    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    login_hint: Mapped[str | None] = mapped_column(String(320), nullable=True)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class OAuthIdentity(AuditedBase):
    """A federated identity ``(provider, subject)`` linked to a user.

    SSO matches on this first; the provider email is only used to *establish*
    the link (once, and only when the provider says it is verified). Global
    like ``oauth_states`` — the tenant is that of the linked user.
    """

    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_oauth_identity_provider_subject"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TokenPurpose(StrEnum):
    RESET = "reset"    # self-service "forgot password"
    INVITE = "invite"  # admin-created account: set the first password


class PasswordResetToken(AuditedBase):
    """Single-use, hashed, expiring token that lets its holder set a password
    (self-service reset or accepting an admin invitation). Global — the flow
    starts before any tenant context exists."""

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    purpose: Mapped[TokenPurpose] = mapped_column(String(12), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


# ─── WebAuthn / passkeys ────────────────────────────────────────────
class WebAuthnCredential(TenantScopedBase):
    """A registered passkey (public-key credential) belonging to a user."""

    __tablename__ = "webauthn_credentials"
    __table_args__ = (
        UniqueConstraint("credential_id", name="uq_webauthn_credential_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    public_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    transports: Mapped[list | None] = mapped_column(JSON, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebAuthnChallenge(AuditedBase):
    """Short-lived challenge for a passkey registration/authentication ceremony
    (global — an authentication ceremony precedes any tenant context)."""

    __tablename__ = "webauthn_challenges"

    challenge: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # registration | authentication
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RegistrationAlert(AuditedBase):
    """Global operational mail queue, committed atomically with each signup."""

    __tablename__ = "registration_alerts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    sample_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_registration_alerts_pending", "sent_at", "next_attempt_at"),)


class PhoneOtpChallenge(AuditedBase):
    """Short-lived, bounded-attempt WhatsApp proof, consumed once."""
    __tablename__ = "phone_otp_challenges"
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
