"""Legal news HTTP endpoints — shared feed with filters (authenticated users)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUserDep, TenantSessionDep
from app.core.pagination import PageParams, page_params
from app.modules.news.models import NewsCategory
from app.modules.news.schemas import NewsItemCreate, NewsItemRead
from app.modules.news.service import NewsService

router = APIRouter(prefix="/news", tags=["Legal News"])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> NewsService:
    return NewsService(session, current.id)


@router.get("", response_model=list[NewsItemRead], summary="Legal news feed (filterable)")
async def list_news(
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
    q: Annotated[str | None, Query()] = None,
    category: Annotated[NewsCategory | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
) -> list[NewsItemRead]:
    items = await _svc(current, session).list(
        query=q, category=category, source=source, limit=page.limit, offset=page.offset
    )
    return [NewsItemRead.model_validate(i) for i in items]


@router.post(
    "",
    response_model=NewsItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a news item to the feed",
)
async def create_news(
    data: NewsItemCreate, current: CurrentUserDep, session: TenantSessionDep
) -> NewsItemRead:
    item = await _svc(current, session).create(data)
    return NewsItemRead.model_validate(item)


@router.get("/{item_id}", response_model=NewsItemRead, summary="A news item")
async def get_news(
    item_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> NewsItemRead:
    item = await _svc(current, session).get(item_id)
    return NewsItemRead.model_validate(item)
