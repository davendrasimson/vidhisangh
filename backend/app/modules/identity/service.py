"""Authentication & account service (business logic, HTTP-agnostic).

Responsibilities:
- Sign-up: atomically provision a tenant and its owner user.
- Login: verify credentials with lockout + optional MFA.
- Token issuance and **refresh-token rotation with reuse detection**.
- MFA (TOTP) enrolment, enable, and verification with hashed backup codes.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import structlog

from app.core import security
from app.core.config import settings
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    status,
)
from app.modules.identity.models import (
    MfaBackupCode,
    RefreshToken,
    User,
)
from app.modules.identity.rbac import DEFAULT_SIGNUP_ROLE
from app.modules.identity.repository import (
    MfaBackupCodeRepository,
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
from app.modules.tenancy.models import PlanTier, Tenant, TenantStatus, TenantType
from app.modules.tenancy.repository import TenantRepository

log = structlog.get_logger("app.auth")

_MAX_FAILED_LOGINS = 5
_LOCKOUT_MINUTES = 15
_BACKUP_CODE_COUNT = 10


def _as_utc(value: datetime) -> datetime:
    """Normalise to timezone-aware UTC (Postgres returns aware; SQLite naive)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


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
        self.tenants = TenantRepository(session)

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
        pair = await self._issue_token_pair(user, ip=ip, user_agent=user_agent, label="signup")
        return user, pair

    # ─── Login ──────────────────────────────────────────────────────
    async def login(
        self, data: LoginRequest, *, ip: str | None = None, user_agent: str | None = None
    ) -> TokenPair:
        user = await self._resolve_login_user(data)
        self._assert_not_locked(user)

        if not user.hashed_password or not security.verify_password(
            data.password, user.hashed_password
        ):
            await self._register_failed_login(user)
            raise AuthenticationError("Invalid email or password.")

        if not user.is_active:
            raise PermissionDeniedError("This account is disabled.")

        if user.mfa_enabled:
            if not data.mfa_code:
                raise MfaRequiredError()
            if not await self._verify_mfa(user, data.mfa_code):
                await self._register_failed_login(user)
                raise AuthenticationError("Invalid MFA code.")

        # Success — reset counters, rotate password hash if params changed.
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = datetime.now(UTC)
        if user.hashed_password and security.password_needs_rehash(user.hashed_password):
            user.hashed_password = security.hash_password(data.password)

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
            # Uniform error + dummy hash keeps timing side-channels closed.
            security.verify_password(data.password, security.hash_password("dummy"))
            raise AuthenticationError("Invalid email or password.")
        return user

    def _assert_not_locked(self, user: User) -> None:
        if user.locked_until and _as_utc(user.locked_until) > datetime.now(UTC):
            raise PermissionDeniedError(
                "Account temporarily locked due to failed login attempts."
            )

    async def _register_failed_login(self, user: User) -> None:
        user.failed_login_count += 1
        if user.failed_login_count >= _MAX_FAILED_LOGINS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=_LOCKOUT_MINUTES)
            log.warning("account_locked", user_id=str(user.id))

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

        access = security.create_access_token(
            subject=str(user.id),
            tenant_id=str(user.tenant_id),
            scopes=sorted(user.permission_codes),
            extra={
                "superuser": user.is_superuser,
                "email": user.email,
                "rtid": str(refresh_row.id),  # the session (refresh-token) this access token belongs to
            },
        )
        return TokenPair(
            access_token=access,
            refresh_token=raw_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
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
        # theft: within the grace window, chain a fresh pair on and move on.
        # Beyond it (or an explicitly revoked token), revoke the whole family.
        now = datetime.now(UTC)
        if stored.replaced_by_id is not None:
            # Rotated and presented again: the theft signal (thief and victim
            # both hold it) — unless it was rotated moments ago (a race).
            elapsed = (now - _as_utc(stored.revoked_at)).total_seconds() if stored.revoked_at else 1e9
            if elapsed > settings.REFRESH_REUSE_GRACE_SECONDS:
                await self.tokens.revoke_all_for_user(stored.user_id)
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

        user = await self.users.get_by_id(stored.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account is no longer active.")

        stored.revoked_at = datetime.now(UTC)
        return await self._issue_token_pair(
            user, ip=ip, user_agent=user_agent, label=stored.device_label, replaces=stored
        )

    async def logout(self, user_id: uuid.UUID, *, raw_refresh: str | None, all_devices: bool) -> None:
        if all_devices:
            await self.tokens.revoke_all_for_user(user_id)
            return
        if raw_refresh:
            stored = await self.tokens.get_active_by_hash(
                security.hash_refresh_token(raw_refresh)
            )
            if stored and stored.user_id == user_id and stored.revoked_at is None:
                stored.revoked_at = datetime.now(UTC)

    # ─── Session / device management ────────────────────────────────
    async def list_sessions(self, user_id: uuid.UUID) -> list[RefreshToken]:
        return await self.tokens.list_active_for_user(user_id)

    async def revoke_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        token = await self.tokens.get_for_user(user_id, session_id)
        if token is None:
            raise NotFoundError("Session not found.")
        if token.revoked_at is None:
            token.revoked_at = datetime.now(UTC)

    async def revoke_other_sessions(
        self, user_id: uuid.UUID, keep_id: uuid.UUID | None
    ) -> int:
        return await self.tokens.revoke_others_for_user(user_id, keep_id)

    # ─── MFA (TOTP) ─────────────────────────────────────────────────
    async def mfa_enroll(self, user: User) -> MfaEnrollResponse:
        secret = pyotp.random_base32()
        user.mfa_secret = secret  # encrypted at rest via EncryptedString
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name=settings.MFA_ISSUER
        )
        return MfaEnrollResponse(secret=secret, otpauth_uri=uri)

    async def mfa_enable(self, user: User, code: str) -> MfaEnableResponse:
        if not user.mfa_secret:
            raise ConflictError("Start MFA enrolment before enabling it.")
        if not pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
            raise AuthenticationError("Invalid MFA code.")
        user.mfa_enabled = True

        raw_codes = [security.generate_numeric_otp(8) for _ in range(_BACKUP_CODE_COUNT)]
        for raw in raw_codes:
            self.backup_codes.add(
                MfaBackupCode(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    code_hash=_hash_backup_code(raw),
                )
            )
        log.info("mfa_enabled", user_id=str(user.id))
        return MfaEnableResponse(mfa_enabled=True, backup_codes=raw_codes)

    async def mfa_disable(self, user: User) -> None:
        user.mfa_enabled = False
        user.mfa_secret = None

    async def _verify_mfa(self, user: User, code: str) -> bool:
        if user.mfa_secret and pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
            return True
        # Fall back to single-use backup codes.
        target = _hash_backup_code(code)
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
        user.hashed_password = security.hash_password(data.new_password)
        # Force re-auth everywhere after a credential change.
        await self.tokens.revoke_all_for_user(user.id)
        log.info("password_changed", user_id=str(user.id))


def _hash_backup_code(code: str) -> str:
    return hashlib.sha256(f"{settings.SECRET_KEY}:backup:{code}".encode()).hexdigest()
