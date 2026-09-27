"""Data-access layer for drafts. Filters by ``tenant_id`` explicitly alongside RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.drafting.models import Draft, DraftVersion


class DraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def get(self, tenant_id: uuid.UUID, draft_id: uuid.UUID) -> Draft | None:
        res = await self.session.execute(
            select(Draft).where(
                Draft.id == draft_id, Draft.tenant_id == tenant_id, Draft.deleted_at.is_(None)
            )
        )
        return res.scalar_one_or_none()

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        matter_id: uuid.UUID | None = None,
        q: str | None = None,
        limit: int = 100,
        client_id: uuid.UUID | None = None,
    ) -> list[Draft]:
        stmt = (
            select(Draft)
            .where(Draft.tenant_id == tenant_id, Draft.deleted_at.is_(None))
            .order_by(Draft.updated_at.desc())
            .limit(limit)
        )
        if matter_id is not None:
            stmt = stmt.where(Draft.matter_id == matter_id)
        if client_id is not None:
            stmt = stmt.where(Draft.client_id == client_id)
        if q:
            stmt = stmt.where(Draft.title.ilike(f"%{q}%"))
        return list((await self.session.execute(stmt)).scalars().all())

    async def versions(self, tenant_id: uuid.UUID, draft_id: uuid.UUID) -> list[DraftVersion]:
        res = await self.session.execute(
            select(DraftVersion)
            .where(DraftVersion.draft_id == draft_id, DraftVersion.tenant_id == tenant_id)
            .order_by(DraftVersion.version_no.desc())
        )
        return list(res.scalars().all())

    async def get_version(
        self, tenant_id: uuid.UUID, draft_id: uuid.UUID, version_id: uuid.UUID
    ) -> DraftVersion | None:
        res = await self.session.execute(
            select(DraftVersion).where(
                DraftVersion.id == version_id,
                DraftVersion.draft_id == draft_id,
                DraftVersion.tenant_id == tenant_id,
            )
        )
        return res.scalar_one_or_none()

    async def next_version_no(self, draft_id: uuid.UUID) -> int:
        res = await self.session.execute(
            select(func.coalesce(func.max(DraftVersion.version_no), 0)).where(
                DraftVersion.draft_id == draft_id
            )
        )
        return int(res.scalar_one()) + 1
