"""Knowledge base HTTP endpoints (RBAC-guarded, tenant-scoped)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.modules.knowledge.models import KnowledgeCategory
from app.modules.knowledge.schemas import (
    KnowledgeCreate,
    KnowledgeRead,
    KnowledgeSummary,
    KnowledgeUpdate,
)
from app.modules.knowledge.service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> KnowledgeService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return KnowledgeService(session, current.id, current.tenant_id)


@router.post(
    "/items",
    response_model=KnowledgeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a knowledge item",
    dependencies=[require_permission("knowledge:create")],
)
async def create_item(
    data: KnowledgeCreate, current: CurrentUserDep, session: TenantSessionDep
) -> KnowledgeRead:
    return KnowledgeRead.model_validate(await _svc(current, session).create(data))


@router.get(
    "/items",
    response_model=list[KnowledgeSummary],
    summary="Search / list the knowledge base",
    dependencies=[require_permission("knowledge:read")],
)
async def list_items(
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
    category: Annotated[KnowledgeCategory | None, Query()] = None,
    practice_area: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> list[KnowledgeSummary]:
    items = await _svc(current, session).list(
        category=category, practice_area=practice_area, query=q, limit=page.limit, offset=page.offset
    )
    return [KnowledgeSummary.model_validate(i) for i in items]


@router.get(
    "/items/{item_id}",
    response_model=KnowledgeRead,
    summary="Knowledge item detail",
    dependencies=[require_permission("knowledge:read")],
)
async def get_item(
    item_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> KnowledgeRead:
    return KnowledgeRead.model_validate(await _svc(current, session).get(item_id))


@router.patch(
    "/items/{item_id}",
    response_model=KnowledgeRead,
    summary="Update a knowledge item",
    dependencies=[require_permission("knowledge:update")],
)
async def update_item(
    item_id: uuid.UUID,
    data: KnowledgeUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> KnowledgeRead:
    return KnowledgeRead.model_validate(await _svc(current, session).update(item_id, data))


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knowledge item",
    dependencies=[require_permission("knowledge:delete")],
)
async def delete_item(
    item_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
