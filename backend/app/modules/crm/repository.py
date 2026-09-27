"""Data-access layer for CRM. Filters by ``tenant_id`` explicitly alongside RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.crm.models import Lead, LeadActivity, LeadSource, LeadStatus


class CrmRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def delete(self, obj: object) -> None:
        await self.session.delete(obj)

    # ── Leads ───────────────────────────────────────────────────────
    async def get_lead(
        self, tenant_id: uuid.UUID, lead_id: uuid.UUID, *, detail: bool = False
    ) -> Lead | None:
        stmt = select(Lead).where(
            Lead.id == lead_id, Lead.tenant_id == tenant_id, Lead.deleted_at.is_(None)
        )
        if detail:
            stmt = stmt.options(selectinload(Lead.activities))
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_leads(
        self,
        tenant_id: uuid.UUID,
        *,
        status: LeadStatus | None,
        source: LeadSource | None,
        limit: int,
        offset: int,
    ) -> list[Lead]:
        stmt = select(Lead).where(Lead.tenant_id == tenant_id, Lead.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(Lead.status == status)
        if source is not None:
            stmt = stmt.where(Lead.source == source)
        res = await self.session.execute(
            stmt.order_by(Lead.created_at.desc()).limit(limit).offset(offset)
        )
        return list(res.scalars().all())

    async def all_leads(self, tenant_id: uuid.UUID) -> list[Lead]:
        res = await self.session.execute(
            select(Lead)
            .where(Lead.tenant_id == tenant_id, Lead.deleted_at.is_(None))
            .order_by(Lead.created_at.desc())
        )
        return list(res.scalars().all())

    async def get_activity(
        self, tenant_id: uuid.UUID, activity_id: uuid.UUID
    ) -> LeadActivity | None:
        res = await self.session.execute(
            select(LeadActivity).where(
                LeadActivity.id == activity_id, LeadActivity.tenant_id == tenant_id
            )
        )
        return res.scalar_one_or_none()

    async def source_stats(
        self, tenant_id: uuid.UUID
    ) -> list[tuple[LeadSource, int, int]]:
        won = func.sum(case((Lead.status == LeadStatus.WON, 1), else_=0))
        res = await self.session.execute(
            select(Lead.source, func.count(), won)
            .where(Lead.tenant_id == tenant_id, Lead.deleted_at.is_(None))
            .group_by(Lead.source)
        )
        return [(row[0], int(row[1]), int(row[2] or 0)) for row in res.all()]
