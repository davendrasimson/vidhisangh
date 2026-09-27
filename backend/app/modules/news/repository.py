"""Data-access layer for the legal news feed (global table)."""

from __future__ import annotations

import uuid

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_utils import LIKE_ESCAPE, contains
from app.modules.news.models import NewsCategory, NewsItem


def permitted_source():
    """Keep excluded competitor content out of list and direct-item views."""
    return (
        ~func.replace(func.lower(NewsItem.source), " ", "").like("%livelaw%")
        & ~func.lower(func.coalesce(NewsItem.url, "")).like("%livelaw.in%")
    )


class NewsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, item: NewsItem) -> None:
        self.session.add(item)

    async def get(self, item_id: uuid.UUID) -> NewsItem | None:
        res = await self.session.execute(
            select(NewsItem).where(NewsItem.id == item_id, NewsItem.deleted_at.is_(None), permitted_source())
        )
        return res.scalar_one_or_none()

    async def list(
        self,
        *,
        query: str | None,
        category: NewsCategory | None,
        source: str | None,
        limit: int,
        offset: int,
    ) -> list[NewsItem]:
        stmt = select(NewsItem).where(NewsItem.deleted_at.is_(None), permitted_source())
        if query:
            like = contains(query)
            stmt = stmt.where(
                or_(
                    NewsItem.title.ilike(like, escape=LIKE_ESCAPE),
                    NewsItem.summary.ilike(like, escape=LIKE_ESCAPE),
                    cast(NewsItem.tags, String).ilike(like, escape=LIKE_ESCAPE),
                )
            )
        if category is not None:
            stmt = stmt.where(NewsItem.category == category)
        if source:
            stmt = stmt.where(NewsItem.source.ilike(contains(source), escape=LIKE_ESCAPE))
        res = await self.session.execute(
            stmt.order_by(NewsItem.published_at.desc()).limit(limit).offset(offset)
        )
        return list(res.scalars().all())
