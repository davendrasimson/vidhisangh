"""Data-access layer for audit events. Filters by ``tenant_id`` alongside RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEvent


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, event: AuditEvent) -> None:
        self.session.add(event)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        action: str | None,
        limit: int,
        offset: int,
    ) -> list[AuditEvent]:
        stmt = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
        if action:
            stmt = stmt.where(AuditEvent.action == action)
        stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
