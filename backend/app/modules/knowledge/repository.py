"""Data-access layer for the knowledge base. Filters by ``tenant_id`` + RLS."""

from __future__ import annotations

import uuid

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_utils import LIKE_ESCAPE, contains
from app.modules.knowledge.models import KnowledgeCategory, KnowledgeItem


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, item: KnowledgeItem) -> None:
        self.session.add(item)

    async def delete(self, item: KnowledgeItem) -> None:
        await self.session.delete(item)

    async def get(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> KnowledgeItem | None:
        res = await self.session.execute(
            select(KnowledgeItem).where(
                KnowledgeItem.id == item_id,
                KnowledgeItem.tenant_id == tenant_id,
                KnowledgeItem.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        category: KnowledgeCategory | None,
        practice_area: str | None,
        query: str | None,
        limit: int,
        offset: int,
    ) -> list[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(
            KnowledgeItem.tenant_id == tenant_id, KnowledgeItem.deleted_at.is_(None)
        )
        if category is not None:
            stmt = stmt.where(KnowledgeItem.category == category)
        if practice_area:
            stmt = stmt.where(KnowledgeItem.practice_area.ilike(contains(practice_area), escape=LIKE_ESCAPE))
        if query:
            like = contains(query)
            stmt = stmt.where(
                or_(
                    KnowledgeItem.title.ilike(like, escape=LIKE_ESCAPE),
                    KnowledgeItem.body.ilike(like, escape=LIKE_ESCAPE),
                    cast(KnowledgeItem.tags, String).ilike(like, escape=LIKE_ESCAPE),
                )
            )
        res = await self.session.execute(
            stmt.order_by(KnowledgeItem.updated_at.desc()).limit(limit).offset(offset)
        )
        return list(res.scalars().all())
