"""Data-access layer for tenants."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tenancy.models import Tenant


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:70] or "tenant"


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        result = await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(
            select(Tenant).where(Tenant.slug == slug, Tenant.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def slug_exists(self, slug: str) -> bool:
        result = await self.session.execute(
            select(func.count()).select_from(Tenant).where(Tenant.slug == slug)
        )
        return (result.scalar_one() or 0) > 0

    async def generate_unique_slug(self, name: str) -> str:
        base = slugify(name)
        candidate = base
        suffix = 1
        while await self.slug_exists(candidate):
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    def add(self, tenant: Tenant) -> None:
        self.session.add(tenant)

    async def flush(self) -> None:
        await self.session.flush()
