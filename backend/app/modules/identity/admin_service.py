"""Admin operations over users within a tenant (invite + role assignment).

Kept separate from the auth-focused ``AuthService`` so the organisation admin
surface (add a user, list roles, set a user's roles) has a clear home. Guards
against self-lockout by refusing to let an admin edit their own roles.

Invitations (audit A-24b): a new user gets a single-use invitation link (7 days)
to set their own password — emailed via the channel seam and returned to the
admin to forward. A temporary password is only returned when
``INVITES_RETURN_TEMP_PASSWORD`` is on, and then the account is flagged
``password_must_change`` so that credential can do nothing but be replaced.
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.apikeys.repository import ApiKeyRepository
from app.modules.audit.service import record_audit
from app.modules.identity.models import Role, TokenPurpose, User
from app.modules.identity.repository import (
    RefreshTokenRepository,
    RoleRepository,
    UserRepository,
)
from app.modules.identity.service import AuthService


def _generate_temp_password() -> str:
    """A strong temporary password (mixed case, digits, symbol) for a new user."""
    return f"Vs{secrets.token_urlsafe(12)}9!"


class UserAdminService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.auth = AuthService(session)

    async def list_roles(self) -> list[Role]:
        return await self.roles.list_assignable(self.tenant_id)

    async def _resolve_roles(self, role_codes: list[str]) -> list[Role]:
        resolved: list[Role] = []
        seen: set[str] = set()
        for code in role_codes:
            if code in seen:
                continue
            seen.add(code)
            role = await self.roles.get_assignable(self.tenant_id, code)
            if role is None:
                raise ValidationError(f"Role '{code}' is not assignable in this organisation.")
            resolved.append(role)
        if not resolved:
            raise ValidationError("A user must have at least one role.")
        return resolved

    async def _require_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_for_tenant(self.tenant_id, user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def create_user(
        self, *, email: str, full_name: str, role_codes: list[str]
    ) -> tuple[User, str | None]:
        """Add a user to the tenant. Returns ``(user, temporary_password)`` where
        the password is ``None`` unless ``INVITES_RETURN_TEMP_PASSWORD`` is on.
        The invitation link is attached to ``user.invitation_url`` (transient)."""
        email = email.lower()
        if await self.users.get_by_email(self.tenant_id, email) is not None:
            raise ConflictError("A user with this email already exists in your organisation.")
        # Emails are unique platform-wide, so an address already used by another
        # organisation cannot be added here either. Deliberately vague about
        # where it is in use — that would leak membership of other tenants.
        if await self.users.email_taken_anywhere(email):
            raise ConflictError(
                "This email is already registered on VidhiSangh and cannot be "
                "added to your organisation."
            )
        roles = await self._resolve_roles(role_codes)
        temp_password = _generate_temp_password()
        user = User(
            tenant_id=self.tenant_id,
            email=email,
            full_name=full_name,
            # Unknown to anyone unless INVITES_RETURN_TEMP_PASSWORD hands it out;
            # either way it must be replaced before the account can be used.
            hashed_password=security.hash_password(temp_password),
            password_must_change=True,
            is_active=True,
            is_email_verified=False,
        )
        for role in roles:
            user.roles.append(role)
        self.users.add(user)
        await self.users.flush()

        # Publish a directory identity so the new user is discoverable, mirroring
        # what self-service registration does.
        from app.modules.network.models import NetworkIdentity

        self.session.add(
            NetworkIdentity(
                user_id=user.id,
                tenant_id=self.tenant_id,
                display_name=user.full_name,
                avatar_url=user.avatar_url,
            )
        )
        await self.session.flush()

        raw = await self.auth.issue_password_token(
            user, purpose=TokenPurpose.INVITE, created_by=self.actor_id
        )
        invitation_url = AuthService.password_token_url(raw, purpose=TokenPurpose.INVITE)
        user.invitation_url = invitation_url  # transient — read by UserCreatedRead
        record_audit(
            self.session,
            tenant_id=self.tenant_id,
            actor_id=self.actor_id,
            action="user.invited",
            summary=f"Invited {user.email} ({', '.join(r.code for r in roles)})",
            entity_type="user",
            entity_id=str(user.id),
            meta={"expires_in_days": settings.INVITE_TOKEN_EXPIRE_DAYS,
                  "temp_password_returned": settings.INVITES_RETURN_TEMP_PASSWORD},
        )
        await self.auth._send_email(
            to_email=user.email,
            to_name=user.full_name,
            subject="You have been invited to VidhiSangh",
            body=(
                f"Hello {user.full_name},\n\nAn administrator has added you to their "
                f"organisation on VidhiSangh. Open the link below to choose your password "
                f"and sign in. It expires in {settings.INVITE_TOKEN_EXPIRE_DAYS} days.\n"
            ),
            link=invitation_url,
        )
        return user, (temp_password if settings.INVITES_RETURN_TEMP_PASSWORD else None)

    async def set_roles(self, user_id: uuid.UUID, role_codes: list[str]) -> User:
        if user_id == self.actor_id:
            raise ValidationError(
                "You cannot change your own roles — ask another administrator."
            )
        user = await self._require_user(user_id)
        user.roles = await self._resolve_roles(role_codes)  # relationship is eagerly loaded
        # Outstanding access tokens still carry the old scopes: deny them now;
        # the next refresh mints a token with the new ones.
        await self.auth._revoke_access_tokens(user)
        return user

    async def set_active(self, user_id: uuid.UUID, active: bool) -> User:
        """Deactivate (disable sign-in) or reactivate a user. Deactivating also
        revokes their sessions, access tokens and API keys so nothing they hold
        keeps working (audit A-19, A-24c)."""
        if user_id == self.actor_id and not active:
            raise ValidationError(
                "You cannot deactivate your own account — ask another administrator."
            )
        user = await self._require_user(user_id)
        user.is_active = active
        if not active:
            await RefreshTokenRepository(self.session).revoke_all_for_user(user_id)
            await ApiKeyRepository(self.session).revoke_all_for_user(self.tenant_id, user_id)
            await self.auth._revoke_access_tokens(user)
        return user
