"""Admin operations over users within a tenant (invite + role assignment).

Kept separate from the auth-focused ``AuthService`` so the organisation admin
surface (add a user, list roles, set a user's roles) has a clear home. Guards
against self-lockout by refusing to let an admin edit their own roles.
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.identity.models import Role, User
from app.modules.identity.repository import (
    RefreshTokenRepository,
    RoleRepository,
    UserRepository,
)


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

    async def create_user(
        self, *, email: str, full_name: str, role_codes: list[str]
    ) -> tuple[User, str]:
        """Add a user to the tenant with a temporary password (returned once)."""
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
            hashed_password=security.hash_password(temp_password),
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
        return user, temp_password

    async def set_roles(self, user_id: uuid.UUID, role_codes: list[str]) -> User:
        if user_id == self.actor_id:
            raise ValidationError(
                "You cannot change your own roles — ask another administrator."
            )
        user = await self.users.get_by_id(user_id)
        if user is None or user.tenant_id != self.tenant_id:
            raise NotFoundError("User not found.")
        user.roles = await self._resolve_roles(role_codes)  # relationship is eagerly loaded
        return user

    async def set_active(self, user_id: uuid.UUID, active: bool) -> User:
        """Deactivate (disable sign-in) or reactivate a user. Deactivating also
        revokes their sessions so existing refresh tokens stop working."""
        if user_id == self.actor_id and not active:
            raise ValidationError(
                "You cannot deactivate your own account — ask another administrator."
            )
        user = await self.users.get_by_id(user_id)
        if user is None or user.tenant_id != self.tenant_id:
            raise NotFoundError("User not found.")
        user.is_active = active
        if not active:
            await RefreshTokenRepository(self.session).revoke_all_for_user(user_id)
        return user
