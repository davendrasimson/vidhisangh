"""Subscription service — resolve the tenant's plan and report usage."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.identity.models import User
from app.modules.matters.models import Matter
from app.modules.plans.catalog import CATALOG_BY_TIER, PLAN_CATALOG
from app.modules.tenancy.models import PlanTier, TenantStatus
from app.modules.tenancy.repository import TenantRepository


class PlansService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.tenants = TenantRepository(session)

    def _plan_dict(self, tier: PlanTier, current: PlanTier) -> dict:
        p = CATALOG_BY_TIER[tier]
        return {
            "tier": p.tier,
            "name": p.name,
            "price_inr": p.price_inr,
            "max_users": p.max_users,
            "max_matters": p.max_matters,
            "storage_gb": p.storage_gb,
            "features": p.features,
            "is_current": tier == current,
        }

    async def _current_tier(self) -> PlanTier:
        tenant = await self.tenants.get_by_id(self.tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found.")
        return tenant.plan

    async def list_plans(self) -> list[dict]:
        current = await self._current_tier()
        return [self._plan_dict(p.tier, current) for p in PLAN_CATALOG]

    async def _count(self, model) -> int:
        res = await self.session.execute(
            select(func.count()).select_from(model).where(
                model.tenant_id == self.tenant_id, model.deleted_at.is_(None)
            )
        )
        return int(res.scalar_one())

    async def get_subscription(self) -> dict:
        tenant = await self.tenants.get_by_id(self.tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found.")
        return {
            "plan": self._plan_dict(tenant.plan, tenant.plan),
            "status": tenant.status,
            "usage": {
                "users": await self._count(User),
                "matters": await self._count(Matter),
            },
        }

    async def change_plan(self, tier: PlanTier) -> dict:
        tenant = await self.tenants.get_by_id(self.tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found.")
        tenant.plan = tier
        # Subscribing to any plan activates the workspace (payment collection for
        # paid tiers is the parked Razorpay go-live step).
        if tenant.status in (TenantStatus.TRIAL, TenantStatus.CANCELLED):
            tenant.status = TenantStatus.ACTIVE
        await self.session.flush()
        return await self.get_subscription()
