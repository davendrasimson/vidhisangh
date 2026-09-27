"""Data-access layer for feature flags. Filters by ``tenant_id`` alongside RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.featureflags.models import FeatureFlag


class FeatureFlagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, flag: FeatureFlag) -> None:
        self.session.add(flag)

    async def list(self, tenant_id: uuid.UUID) -> list[FeatureFlag]:
        res = await self.session.execute(
            select(FeatureFlag).where(FeatureFlag.tenant_id == tenant_id)
        )
        return list(res.scalars().all())

    async def get(self, tenant_id: uuid.UUID, key: str) -> FeatureFlag | None:
        res = await self.session.execute(
            select(FeatureFlag).where(
                FeatureFlag.tenant_id == tenant_id, FeatureFlag.key == key
            )
        )
        return res.scalar_one_or_none()
