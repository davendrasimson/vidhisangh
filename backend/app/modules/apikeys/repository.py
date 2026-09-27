"""Data-access layer for API keys. Filters by ``tenant_id`` alongside RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.apikeys.models import ApiKey


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, key: ApiKey) -> None:
        self.session.add(key)

    async def list(self, tenant_id: uuid.UUID) -> list[ApiKey]:
        res = await self.session.execute(
            select(ApiKey)
            .where(ApiKey.tenant_id == tenant_id, ApiKey.deleted_at.is_(None))
            .order_by(ApiKey.created_at.desc())
        )
        return list(res.scalars().all())

    async def get(self, tenant_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey | None:
        res = await self.session.execute(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.tenant_id == tenant_id,
                ApiKey.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        """Cross-tenant lookup by hash (used during authentication, pre-tenant)."""
        res = await self.session.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.deleted_at.is_(None))
        )
        return res.scalar_one_or_none()
