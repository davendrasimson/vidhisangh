"""Authentication & account service (business logic, HTTP-agnostic).

Responsibilities:
- Sign-up: atomically provision a tenant and its owner user.
- Login: verify credentials with lockout + optional MFA.
- Token issuance and **refresh-token rotation with reuse detection**.
- MFA (TOTP) enrolment, enable, disable and verification with hashed backup codes.
- Password change / reset / invitation acceptance, email verification.
- Security audit events for every credential-related action (audit A-20).

Transactions: the request session commits on success and rolls back on an
error response. Anything that must survive a *failing* request — the failed
login counter, lockout, refresh-reuse revocation, OAuth state consumption —
is committed explicitly before the error is raised (audit A-1, A-23).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import structlog

from app.core import security
from app.core.channels import ChannelMessage, get_channels
from app.core.config import settings
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
    status,
)
from app.core.revocation import mark_user_revoked
from app.modules.audit.service import record_audit
from app.modules.identity.models import (
    MfaBackupCode,
    PasswordResetToken,
    RefreshToken,
    TokenPurpose,
    User,
)
from app.modules.identity.rbac import DEFAULT_SIGNUP_ROLE
from app.modules.identity.repository import (
    MfaBackupCodeRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
    RoleRepository,
    UserRepository,
)
from app.modules.identity.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MfaEnableResponse,
    MfaEnrollResponse,
    RegisterRequest,
    TokenPair,
)
from app.modules.notifications.models import NotificationChannel
from app.modules.tenancy.models import PlanTier, Tenant, TenantStatus, TenantType
from app.modules.tenancy.repository import TenantRepository

log = structlog.get_logger("app.auth")


def _current_terms_version() -> str:
    """Privacy agent: the Terms/Notice version a new sign-up accepts (single
    import point so the identity module does not depend on privacy config)."""
    from app.modules.privacy.config import privacy_setting

    return str(privacy_setting("CURRENT_TERMS_VERSION"))


_BACKUP_CODE_COUNT = 10


def _as_utc(value: datetime) -> datetime:
    """Normalise to timezone-aware UTC (Postgres returns aware; SQLite naive)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _app_link(path: str) -> str:
    return f"{settings.PUBLIC_APP_URL.rstrip('/')}{path}"


class MfaRequiredError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "mfa_required"
    message = "Multi-factor authentication code required."


class RefreshTokenReuseError(AuthenticationError):
    code = "refresh_reuse_detected"
    message = "Refresh token reuse detected — all sessions revoked. Please sign in again."


class AuthService:
    """Coordinates identity repositories within a single unit of work."""

    def __init__(self, session) -> None:  # noqa: ANN001 - AsyncSession
        self.session = session
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.backup_codes = MfaBackupCodeRepository(session)
        self.reset_tokens = PasswordResetTokenRepository(session)
        self.tenants = TenantRepository(session)

    # ─── Audit helper ───────────────────────────────────────────────
    def _audit(
        self,
        user: User,
        action: str,
        summary: str,
        *,
        meta: dict | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        record_audit(
            self.session,
            tenant_id=user.tenant_id,
            actor_id=actor_id or user.id,
            actor_label=user.email,
            action=action,
            summary=summary,
            entity_type="user",
            entity_id=str(user.id),
            meta=meta,
        )

    async def _revoke_access_tokens(self, user: User) -> None:
        """Invalidate every outstanding *access* token immediately (see revocation.py)."""
        user.token_epoch = (user.token_epoch or 0) + 1
        await mark_user_revoked(user.id, user.token_epoch)

    # ─── Registration ───────────────────────────────────────────────
    async def register(
        self, data: RegisterRequest, *, ip: str | None = None, user_agent: str | None = None
    ) -> tuple[User, TokenPair]:
        # Emails are unique platform-wide, so check before creating the tenant —
        # otherwise a rejected signup would leave an empty organisation behind.
        if await self.users.email_taken_anywhere(data.email):
            raise ConflictError(
                "An account with this email already exists. Sign in instead, or "
                "use a different address for this organisation."
            )

        slug = await self.tenants.generate_unique_slug(data.organisation_name)
        tenant = Tenant(
            name=data.organisation_name,
            slug=slug,
            type=TenantType.INDIVIDUAL,
            status=TenantStatus.TRIAL,
            plan=PlanTier.FREE,
            primary_contact_email=data.email.lower(),
        )
        self.tenants.add(tenant)
        await self.tenants.flush()  # assign tenant.id

        user = User(
            tenant_id=tenant.id,
            email=data.email.lower(),
            full_name=data.full_name,
            hashed_password=security.hash_password(data.password),
            is_active=True,
            is_email_verified=False,
            # ── privacy agent: persist the terms acceptance (DPDP s.6) ──
            terms_version=str(_current_terms_version()),
            terms_accepted_at=datetime.now(UTC),
            # ── end privacy block ──
        )
        owner_role = await self.roles.get_system_role(DEFAULT_SIGNUP_ROLE)
        if owner_role is not None:
            user.roles.append(owner_role)
        self.users.add(user)
        await self.users.flush()

        # Publish a directory identity so the user is discoverable in the
        # (cross-tenant) professional network from day one.
        from app.modules.network.models import NetworkIdentity

        self.session.add(
            NetworkIdentity(
                user_id=user.id,
                tenant_id=tenant.id,
                display_name=user.full_name,
                avatar_url=user.avatar_url,
            )
        )
        await self.session.flush()

        log.info("tenant_registered", tenant_id=str(tenant.id), user_id=str(user.id))
        self._audit(user, "auth.registered", f"Registered organisation {tenant.name}", meta={"ip": ip})
        await self.send_email_verification(user)
        pair = await self._issue_token_pair(user, ip=ip, user_agent=user_agent, label="signup")
        return user, pair

    async def accept_current_terms(self, user: User) -> User:
        """Record an explicit acceptance of the currently published legal terms."""
        previous = user.terms_version
        user.terms_version = _current_terms_version()
        user.terms_accepted_at = datetime.now(UTC)
        self._audit(
            user,
            "privacy.terms_accepted",
            f"Accepted Terms and Privacy Notice version {user.terms_version}",
            meta={"previous_version": previous, "accepted_version": user.terms_version},
        )
        await self.session.flush()
        return user

    # ─── Email verification ─────────────────────────────────────────
    async def send_email_verification(self, user: User) -> str:
        """Issue a fresh verification token and email the link. Returns the raw
        token (for tests / the log provider); the DB holds only its hash."""
        raw = security.generate_url_safe_token(32)
        user.email_verification_token_hash = security.hash_link_token(raw)
        user.email_verification_expires_at = datetime.now(UTC) + timedelta(
            hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS
        )
        await self._send_email(
            to_email=user.email,
            to_name=user.full_name,
            subject="Verify your VidhiSangh email address",
            body=(
                f"Hello {user.full_name},\n\nPlease confirm this email address for your "
                f"VidhiSangh account by opening the link below. It expires in "
                f"{settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours.\n"
            ),
            link=_app_link(f"/auth/verify-email/{raw}"),
        )
        return raw

    async def verify_email(self, raw_token: str) -> User:
        user = await self.users.get_by_verification_hash(security.hash_link_token(raw_token))
        if user is None or user.email_verification_expires_at is None:
            raise NotFoundError("This verification link is invalid or has already been used.")
        if _as_utc(user.email_verification_expires_at) < datetime.now(UTC):
            raise ValidationError("This verification link has expired. Sign in and request a new one.")
        user.is_email_verified = True
        user.email_verification_token_hash = None
        user.email_verification_expires_at = None
        self._audit(user, "auth.email_verified", "Email address verified")
        return user

    async def _send_email(
        self, *, to_email: str, to_name: str | None, subject: str, body: str, link: str
    ) -> None:
        provider = get_channels().provider_for(NotificationChannel.EMAIL)
        if provider is None:
            return
        try:
            await provider.send(
                ChannelMessage(to_email=to_email, to_name=to_name, subject=subject, body=body, link=link)
            )
        except Exception as exc:  # noqa: BLE001 - never fail auth on mail trouble
            log.warning("auth_email_failed", subject=subject, error=str(exc))

    # ─── Login ──────────────────────────────────────────────────────
    async def login(
        self, data: LoginRequest, *, ip: str | None = None, user_agent: str | None = None
    ) -> TokenPair:
        user = await self._resolve_login_user(data)
        self._assert_not_locked(user)

        if not user.hashed_password or not security.verify_password(
            data.password, user.hashed_password
        ):
            await self._register_failed_login(user, reason="password", ip=ip)
            raise AuthenticationError("Invalid email or password.")

        if not user.is_active:
            raise PermissionDeniedError("This account is disabled.")

        if user.mfa_enabled:
            if not data.mfa_code:
                raise MfaRequiredError()
            if not await self._verify_mfa(user, data.mfa_code):
                await self._register_failed_login(user, reason="mfa", ip=ip)
                raise AuthenticationError("Invalid MFA code.")

        # Success — reset counters, rotate password hash if params changed.
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = datetime.now(UTC)
        if user.hashed_password and security.password_needs_rehash(user.hashed_password):
            user.hashed_password = security.hash_password(data.password)

        self._audit(
            user, "auth.login", "Signed in",
            meta={"ip": ip, "mfa": user.mfa_enabled, "device": data.device_label},
        )
        return await self._issue_token_pair(
            user, ip=ip, user_agent=user_agent, label=data.device_label or "login"
        )

    async def issue_tokens_for_user(
        self, user: User, *, ip: str | None = None, user_agent: str | None = None, label: str | None = None
    ) -> TokenPair:
        """Issue a token pair for an already-authenticated user (e.g. via SSO)."""
        return await self._issue_token_pair(user, ip=ip, user_agent=user_agent, label=label)

    async def _resolve_login_user(self, data: LoginRequest) -> User:
        if data.tenant_slug:
            tenant = await self.tenants.get_by_slug(data.tenant_slug)
            if tenant is None:
                raise AuthenticationError("Invalid email or password.")
            user = await self.users.get_by_email(tenant.id, data.email)
        else:
            # An email maps to exactly one account (users_email_global_unique),
            # so no tenant hint is needed to sign in.
            candidates = await self.users.find_by_email_global(data.email)
            user = candidates[0] if candidates else None
        if user is None:
            # Uniform error + dummy verification keeps timing side-channels closed.
            security.verify_password(data.password, security.dummy_password_hash())
            raise AuthenticationError("Invalid email or password.")
        return user

    def _assert_not_locked(self, user: User) -> None:
        if user.locked_until and _as_utc(user.locked_until) > datetime.now(UTC):
            raise PermissionDeniedError(
                "Account temporarily locked due to failed login attempts."
            )

    async def _register_failed_login(self, user: User, *, reason: str, ip: str | None) -> None:
        """Count a failure and **commit** it: the 401 that follows rolls the
        request back, which used to discard the counter (audit A-1)."""
        user.failed_login_count = (user.failed_login_count or 0) + 1
        self._audit(
            user, "auth.login_failed", f"Failed sign-in ({reason})",
            meta={"ip": ip, "reason": reason, "attempt": user.failed_login_count},
        )
        if user.failed_login_count >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            log.warning("account_locked", user_id=str(user.id))
            self._audit(
                user, "auth.lockout",
                f"Account locked for {settings.LOGIN_LOCKOUT_MINUTES} minutes after "
                f"{user.failed_login_count} failed attempts",
                meta={"ip": ip, "until": user.locked_until.isoformat()},
            )
        await self.session.commit()

    # ─── Token issuance & rotation ──────────────────────────────────
    async def _issue_token_pair(
        self,
        user: User,
        *,
        ip: str | None,
        user_agent: str | None,
        label: str | None,
        replaces: RefreshToken | None = None,
    ) -> TokenPair:
        raw_refresh = security.generate_refresh_token()
        refresh_row = RefreshToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=security.hash_refresh_token(raw_refresh),
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            device_label=label,
            ip_address=ip,
            user_agent=(user_agent or "")[:400] or None,
        )
        self.tokens.add(refresh_row)
        await self.session.flush()  # assign refresh_row.id so the access token can name its session
        if replaces is not None:
            replaces.replaced_by_id = refresh_row.id

        extra = {
            "superuser": user.is_superuser,
            "email": user.email,
            "rtid": str(refresh_row.id),  # the session (refresh-token) this access token belongs to
            "ep": user.token_epoch or 0,
        }
        if user.password_must_change:
            extra["pmc"] = True
        access = security.create_access_token(
            subject=str(user.id),
            tenant_id=str(user.tenant_id),
            scopes=sorted(user.permission_codes),
            extra=extra,
        )
        return TokenPair(
            access_token=access,
            refresh_token=raw_refresh,  # the router moves it into the cookie
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            password_must_change=bool(user.password_must_change),
        )

    async def refresh(
        self, raw_refresh: str, *, ip: str | None = None, user_agent: str | None = None
    ) -> TokenPair:
        token_hash = security.hash_refresh_token(raw_refresh)
        stored = await self.tokens.get_active_by_hash(token_hash)
        if stored is None:
            raise AuthenticationError("Invalid refresh token.")

        # Reuse detection: a revoked-but-presented token means it was stolen —
        # unless it was rotated moments ago. The access token is held only in
        # memory, so every hard refresh and every new tab presents the stored
        # refresh token; two tabs booting together, or a reload that lands
        # mid-rotation, present the same one twice. That is a race, not a
        # theft: within the grace window — and only from the same user agent
        # (audit A-23) — chain a fresh pair on and move on. Beyond it (or an
        # explicitly revoked token), revoke the whole family.
        now = datetime.now(UTC)
        if stored.replaced_by_id is not None:
            elapsed = (now - _as_utc(stored.revoked_at)).total_seconds() if stored.revoked_at else 1e9
            same_agent = ((user_agent or "")[:400] or None) == stored.user_agent
            if elapsed > settings.REFRESH_REUSE_GRACE_SECONDS or not same_agent:
                await self.tokens.revoke_all_for_user(stored.user_id)
                victim = await self.users.get_by_id_global(stored.user_id)
                if victim is not None:
                    await self._revoke_access_tokens(victim)
                    self._audit(
                        victim, "auth.refresh_reuse",
                        "Refresh token reuse detected — every session revoked",
                        meta={"ip": ip, "same_user_agent": same_agent, "elapsed_s": int(min(elapsed, 1e9))},
                    )
                # Commit before raising: the error response rolls the request's
                # transaction back, which silently undid the revocation — the
                # "stolen" family stayed valid. (Found by asserting it.)
                await self.session.commit()
                log.warning("refresh_reuse", user_id=str(stored.user_id))
                raise RefreshTokenReuseError()
            log.info("refresh_race", user_id=str(stored.user_id))
        elif stored.revoked_at is not None:
            # Signed out (logout, revoke-others, password change): the device
            # will naturally present this token on its next boot. Plain 401 —
            # not a reason to sign out every other device.
            raise AuthenticationError("Refresh token revoked.")

        if _as_utc(stored.expires_at) <= datetime.now(UTC):
            raise AuthenticationError("Refresh token expired.")

        user = await self.users.get_by_id_global(stored.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account is no longer active.")

        stored.revoked_at = datetime.now(UTC)
        # The rotated token keeps ip/user_agent: the reuse-grace check compares
        # them (A-23). The nightly retention purge clears them after 30 days.
        return await self._issue_token_pair(
            user, ip=ip, user_agent=user_agent, label=stored.device_label, replaces=stored
        )

    async def logout(
        self,
        user_id: uuid.UUID,
        *,
        raw_refresh: str | None,
        all_devices: bool,
        session_id: uuid.UUID | None = None,
    ) -> int:
        """Revoke the presented refresh token (or, absent one, the session the
        access token names via ``rtid``), or every session. Returns how many
        sessions were revoked — 0 means nothing matched."""
        user = await self.users.get_by_id_global(user_id)
        if all_devices:
            revoked = await self.tokens.revoke_all_for_user(user_id)
            if user is not None:
                await self._revoke_access_tokens(user)
                self._audit(user, "auth.logout", "Signed out of all devices", meta={"sessions": revoked})
            return revoked
        stored: RefreshToken | None = None
        if raw_refresh:
            stored = await self.tokens.get_active_by_hash(security.hash_refresh_token(raw_refresh))
        elif session_id is not None:
            stored = await self.tokens.get_for_user(user_id, session_id)
        if stored is None or stored.user_id != user_id or stored.revoked_at is not None:
            return 0
        stored.revoked_at = datetime.now(UTC)
        stored.ip_address = None  # P-14: no login-location history after revocation
        stored.user_agent = None
        if user is not None:
            self._audit(user, "auth.logout", "Signed out", meta={"session_id": str(stored.id)})
        return 1

    # ─── Session / device management ────────────────────────────────
    async def list_sessions(self, user_id: uuid.UUID) -> list[RefreshToken]:
        return await self.tokens.list_active_for_user(user_id)

    async def revoke_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        token = await self.tokens.get_for_user(user_id, session_id)
        if token is None:
            raise NotFoundError("Session not found.")
        if token.revoked_at is None:
            token.revoked_at = datetime.now(UTC)
            token.ip_address = None  # P-14: no login-location history after revocation
            token.user_agent = None
            user = await self.users.get_by_id_global(user_id)
            if user is not None:
                self._audit(
                    user, "auth.session_revoked", "Revoked a signed-in device",
                    meta={"session_id": str(session_id), "device": token.device_label},
                )

    async def revoke_other_sessions(
        self, user_id: uuid.UUID, keep_id: uuid.UUID | None
    ) -> int:
        count = await self.tokens.revoke_others_for_user(user_id, keep_id)
        user = await self.users.get_by_id_global(user_id)
        if user is not None and count:
            self._audit(user, "auth.sessions_revoked_others", "Signed out of other devices", meta={"sessions": count})
        return count

    # ─── MFA (TOTP) ─────────────────────────────────────────────────
    async def mfa_enroll(self, user: User) -> MfaEnrollResponse:
        """Start (or restart) enrolment. The new secret stays *pending* until
        ``mfa_enable`` proves the authenticator works, so an enabled account is
        never left with a secret the user has not set up. Any previous backup
        codes are discarded now (audit A-18)."""
        secret = pyotp.random_base32()
        user.mfa_pending_secret = secret  # encrypted at rest via EncryptedString
        await self.backup_codes.delete_all_for_user(user.id)
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name=settings.MFA_ISSUER
        )
        self._audit(user, "auth.mfa_enrolled", "Started MFA enrolment")
        return MfaEnrollResponse(secret=secret, otpauth_uri=uri)

    async def mfa_enable(self, user: User, code: str) -> MfaEnableResponse:
        secret = user.mfa_pending_secret
        if not secret:
            raise ConflictError("Start MFA enrolment before enabling it.")
        if not pyotp.TOTP(secret).verify(code.strip(), valid_window=1):
            raise AuthenticationError("Invalid MFA code.")
        user.mfa_secret = secret
        user.mfa_pending_secret = None
        user.mfa_enabled = True

        await self.backup_codes.delete_all_for_user(user.id)
        raw_codes = [security.generate_numeric_otp(8) for _ in range(_BACKUP_CODE_COUNT)]
        for raw in raw_codes:
            self.backup_codes.add(
                MfaBackupCode(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    code_hash=security.hash_backup_code(raw),
                )
            )
        log.info("mfa_enabled", user_id=str(user.id))
        self._audit(user, "auth.mfa_enabled", "Enabled MFA (TOTP)")
        return MfaEnableResponse(mfa_enabled=True, backup_codes=raw_codes)

    async def mfa_disable(self, user: User, *, password: str, code: str) -> None:
        """Both factors are required to turn the second one off (audit A-18)."""
        if not user.hashed_password or not security.verify_password(password, user.hashed_password):
            raise AuthenticationError("Current password is incorrect.")
        if not user.mfa_enabled:
            raise ConflictError("MFA is not enabled.")
        if not await self._verify_mfa(user, code):
            raise AuthenticationError("Invalid MFA code.")
        user.mfa_enabled = False
        user.mfa_secret = None
        user.mfa_pending_secret = None
        await self.backup_codes.delete_all_for_user(user.id)
        self._audit(user, "auth.mfa_disabled", "Disabled MFA")

    async def _verify_mfa(self, user: User, code: str) -> bool:
        code = code.strip().replace(" ", "")
        if user.mfa_secret and pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
            return True
        # Fall back to single-use backup codes.
        target = security.hash_backup_code(code)
        for backup in await self.backup_codes.list_unused_for_user(user.id):
            if security.constant_time_compare(backup.code_hash, target):
                backup.used_at = datetime.now(UTC)
                return True
        return False

    # ─── Password change ────────────────────────────────────────────
    async def change_password(self, user: User, data: ChangePasswordRequest) -> None:
        if not user.hashed_password or not security.verify_password(
            data.current_password, user.hashed_password
        ):
            raise AuthenticationError("Current password is incorrect.")
        if security.verify_password(data.new_password, user.hashed_password):
            raise ValidationError("The new password must differ from the current one.")
        user.hashed_password = security.hash_password(data.new_password)
        user.password_must_change = False
        # Force re-auth everywhere after a credential change.
        await self.tokens.revoke_all_for_user(user.id)
        await self.reset_tokens.invalidate_for_user(user.id)
        await self._revoke_access_tokens(user)
        log.info("password_changed", user_id=str(user.id))
        self._audit(user, "auth.password_changed", "Changed password (all sessions signed out)")

    # ─── Password reset / invitation (audit A-24) ───────────────────
    async def issue_password_token(
        self, user: User, *, purpose: TokenPurpose, created_by: uuid.UUID | None = None
    ) -> str:
        """Create a single-use token; returns the raw value (the DB stores the hash)."""
        await self.reset_tokens.invalidate_for_user(user.id)
        raw = security.generate_url_safe_token(32)
        lifetime = (
            timedelta(days=settings.INVITE_TOKEN_EXPIRE_DAYS)
            if purpose == TokenPurpose.INVITE
            else timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
        )
        self.reset_tokens.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=security.hash_link_token(raw),
                purpose=purpose,
                expires_at=datetime.now(UTC) + lifetime,
                created_by=created_by,
            )
        )
        await self.session.flush()
        return raw

    @staticmethod
    def password_token_url(raw: str, *, purpose: TokenPurpose) -> str:
        suffix = "?invite=1" if purpose == TokenPurpose.INVITE else ""
        return _app_link(f"/auth/reset/{raw}{suffix}")

    async def request_password_reset(self, email: str, *, ip: str | None = None) -> None:
        """Always succeeds from the caller's point of view (no account enumeration)."""
        candidates = await self.users.find_by_email_global(email)
        user = candidates[0] if candidates else None
        if user is None or not user.is_active:
            log.info("password_reset_requested_unknown")
            return
        raw = await self.issue_password_token(user, purpose=TokenPurpose.RESET)
        self._audit(user, "auth.password_reset_requested", "Requested a password reset", meta={"ip": ip})
        await self._send_email(
            to_email=user.email,
            to_name=user.full_name,
            subject="Reset your VidhiSangh password",
            body=(
                f"Hello {user.full_name},\n\nSomeone asked to reset the password for this "
                f"account. If that was you, open the link below within "
                f"{settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes. If not, ignore this email — "
                f"your password has not changed.\n"
            ),
            link=self.password_token_url(raw, purpose=TokenPurpose.RESET),
        )

    async def reset_password(self, raw_token: str, new_password: str, *, ip: str | None = None) -> User:
        row = await self.reset_tokens.get_by_hash(security.hash_link_token(raw_token))
        if row is None or row.used_at is not None:
            raise NotFoundError("This link is invalid or has already been used.")
        if _as_utc(row.expires_at) < datetime.now(UTC):
            raise ValidationError("This link has expired. Please request a new one.")
        user = await self.users.get_by_id_global(row.user_id)
        if user is None or not user.is_active:
            raise NotFoundError("This link is invalid or has already been used.")
        row.used_at = datetime.now(UTC)
        user.hashed_password = security.hash_password(new_password)
        user.password_must_change = False
        user.failed_login_count = 0
        user.locked_until = None
        if row.purpose == TokenPurpose.INVITE:
            # The link reached the mailbox the admin invited, which verifies it.
            user.is_email_verified = True
        await self.tokens.revoke_all_for_user(user.id)
        await self.reset_tokens.invalidate_for_user(user.id)
        await self._revoke_access_tokens(user)
        if row.purpose == TokenPurpose.INVITE:
            self._audit(user, "auth.invite_accepted", "Accepted invitation and set a password", meta={"ip": ip})
        else:
            self._audit(
                user, "auth.password_reset",
                "Password reset via emailed link (all sessions signed out)", meta={"ip": ip},
            )
        return user
