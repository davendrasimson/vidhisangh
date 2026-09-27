"""Legal news service."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.news.models import NewsCategory, NewsItem
from app.modules.news.repository import NewsRepository
from app.modules.news.schemas import NewsItemCreate


class NewsService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.repo = NewsRepository(session)

    async def create(self, data: NewsItemCreate) -> NewsItem:
        item = NewsItem(
            title=data.title,
            summary=data.summary,
            source=data.source,
            category=data.category,
            url=data.url,
            published_at=data.published_at,
            tags=data.tags,
            added_by=self.user_id,
        )
        self.repo.add(item)
        await self.session.flush()
        return item

    async def get(self, item_id: uuid.UUID) -> NewsItem:
        item = await self.repo.get(item_id)
        if item is None:
            raise NotFoundError("News item not found.")
        return item

    async def list(
        self,
        *,
        query: str | None,
        category: NewsCategory | None,
        source: str | None,
        limit: int,
        offset: int,
    ) -> list[NewsItem]:
        return await self.repo.list(
            query=query, category=category, source=source, limit=limit, offset=offset
        )
