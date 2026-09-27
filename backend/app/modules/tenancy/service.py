"""Tenant service — organisation lifecycle operations."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.tenancy.models import Tenant
from app.modules.tenancy.repository import TenantRepository
from app.modules.tenancy.schemas import TenantUpdate


class TenantService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = TenantRepository(session)

    async def get(self, tenant_id: uuid.UUID) -> Tenant:
        tenant = await self.repo.get_by_id(tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found.")
        return tenant

    async def update(self, tenant_id: uuid.UUID, data: TenantUpdate) -> Tenant:
        tenant = await self.get(tenant_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(tenant, field, value)
        return tenant
