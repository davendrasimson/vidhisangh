"""Data-access layer for identity aggregates (Repository pattern).

Repositories encapsulate all SQL for a bounded context, keeping the service
layer persistence-agnostic and independently testable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.identity.models import (
    MfaBackupCode,
    Permission,
    RefreshToken,
    Role,
    User,
)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self, tenant_id: uuid.UUID, limit: int, offset: int
    ) -> list[User]:
        result = await self.session.execute(
            select(User)
            .where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
            .options(selectinload(User.roles).selectinload(Role.permissions))
            .order_by(User.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_email(self, tenant_id: uuid.UUID, email: str) -> User | None:
        result = await self.session.execute(
            select(User)
            .where(
                User.tenant_id == tenant_id,
                User.email == email.lower(),
                User.deleted_at.is_(None),
            )
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    async def find_by_email_global(self, email: str) -> list[User]:
        """Find matching users across tenants (used when no tenant is supplied)."""
        result = await self.session.execute(
            select(User)
            .where(User.email == email.lower(), User.deleted_at.is_(None))
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        return list(result.scalars().all())

    async def email_taken_anywhere(self, email: str) -> bool:
        """True if ANY tenant already has an active user with this address.

        Emails are globally unique (``users_email_global_unique``), so callers
        check this before creating a user to fail with a clear message rather
        than an IntegrityError.
        """
        result = await self.session.execute(
            select(User.id)
            .where(User.email == email.lower(), User.deleted_at.is_(None))
            .limit(1)
        )
        return result.first() is not None

    def add(self, user: User) -> None:
        self.session.add(user)

    async def flush(self) -> None:
        await self.session.flush()


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_system_role(self, code: str) -> Role | None:
        result = await self.session.execute(
            select(Role)
            .where(Role.code == code, Role.tenant_id.is_(None))
            .options(selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    async def get_for_tenant(self, tenant_id: uuid.UUID, code: str) -> Role | None:
        result = await self.session.execute(
            select(Role)
            .where(Role.code == code, Role.tenant_id == tenant_id)
            .options(selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    async def list_permissions(self) -> list[Permission]:
        result = await self.session.execute(select(Permission))
        return list(result.scalars().all())

    # The platform superuser role must never be tenant-assignable.
    _NON_ASSIGNABLE = ("system_admin",)

    async def list_assignable(self, tenant_id: uuid.UUID) -> list[Role]:
        """Roles a tenant admin may grant: built-in system roles + this tenant's
        own custom roles, excluding the platform superuser role."""
        result = await self.session.execute(
            select(Role)
            .where(
                or_(Role.tenant_id.is_(None), Role.tenant_id == tenant_id),
                Role.code.notin_(self._NON_ASSIGNABLE),
            )
            .options(selectinload(Role.permissions))
            .order_by(Role.is_system.desc(), Role.name.asc())
        )
        return list(result.scalars().all())

    async def get_assignable(self, tenant_id: uuid.UUID, code: str) -> Role | None:
        """Resolve an assignable role by code — a tenant custom role takes
        precedence over a same-named system role. Returns ``None`` if forbidden."""
        if code in self._NON_ASSIGNABLE:
            return None
        return await self.get_for_tenant(tenant_id, code) or await self.get_system_role(code)


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    def add(self, token: RefreshToken) -> None:
        self.session.add(token)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        now = datetime.now(UTC)
        for token in result.scalars().all():
            token.revoked_at = now

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[RefreshToken]:
        result = await self.session.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(UTC),
            )
            .order_by(RefreshToken.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(
        self, user_id: uuid.UUID, token_id: uuid.UUID
    ) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.id == token_id, RefreshToken.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def revoke_others_for_user(
        self, user_id: uuid.UUID, keep_id: uuid.UUID | None
    ) -> int:
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        now = datetime.now(UTC)
        count = 0
        for token in result.scalars().all():
            if token.id == keep_id:
                continue
            token.revoked_at = now
            count += 1
        return count


class MfaBackupCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_unused_for_user(self, user_id: uuid.UUID) -> list[MfaBackupCode]:
        result = await self.session.execute(
            select(MfaBackupCode).where(
                MfaBackupCode.user_id == user_id, MfaBackupCode.used_at.is_(None)
            )
        )
        return list(result.scalars().all())

    def add(self, code: MfaBackupCode) -> None:
        self.session.add(code)
