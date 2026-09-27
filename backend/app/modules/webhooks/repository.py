"""Data-access layer for webhooks. Filters by ``tenant_id`` alongside RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.webhooks.models import WebhookDelivery, WebhookEndpoint


class WebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def delete(self, endpoint: WebhookEndpoint) -> None:
        await self.session.delete(endpoint)

    async def list(self, tenant_id: uuid.UUID) -> list[WebhookEndpoint]:
        res = await self.session.execute(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.tenant_id == tenant_id, WebhookEndpoint.deleted_at.is_(None))
            .order_by(WebhookEndpoint.created_at.desc())
        )
        return list(res.scalars().all())

    async def get(self, tenant_id: uuid.UUID, endpoint_id: uuid.UUID) -> WebhookEndpoint | None:
        res = await self.session.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == endpoint_id,
                WebhookEndpoint.tenant_id == tenant_id,
                WebhookEndpoint.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def active_for_event(
        self, tenant_id: uuid.UUID, event_type: str
    ) -> list[WebhookEndpoint]:
        res = await self.session.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.tenant_id == tenant_id,
                WebhookEndpoint.deleted_at.is_(None),
                WebhookEndpoint.is_active.is_(True),
            )
        )
        # event_types is a JSON list — filter in Python for SQLite/PG portability.
        return [e for e in res.scalars().all() if event_type in (e.event_types or [])]

    async def list_deliveries(
        self, tenant_id: uuid.UUID, endpoint_id: uuid.UUID, limit: int, offset: int
    ) -> list[WebhookDelivery]:
        res = await self.session.execute(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.tenant_id == tenant_id,
                WebhookDelivery.endpoint_id == endpoint_id,
            )
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())
