"""Marketplace HTTP endpoints (RBAC-guarded, cross-tenant board)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_flag, require_permission
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.modules.marketplace.models import ListingStatus, ListingType
from app.modules.marketplace.schemas import (
    ListingCreate,
    ListingRead,
    ResponseCreate,
    ResponseRead,
)
from app.modules.marketplace.service import MarketplaceService

router = APIRouter(prefix="/marketplace", tags=["Marketplace"], dependencies=[require_flag("marketplace")])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> MarketplaceService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return MarketplaceService(session, current.id, current.tenant_id)


@router.post(
    "/listings",
    response_model=ListingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Post a listing",
    dependencies=[require_permission("marketplace:create")],
)
async def create_listing(
    data: ListingCreate, current: CurrentUserDep, session: TenantSessionDep
) -> ListingRead:
    return ListingRead.model_validate(await _svc(current, session).create_listing(data))


@router.get(
    "/listings",
    response_model=list[ListingRead],
    summary="Browse listings",
    dependencies=[require_permission("marketplace:read")],
)
async def browse(
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
    type_filter: Annotated[ListingType | None, Query(alias="type")] = None,
    practice_area: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    status_filter: Annotated[ListingStatus | None, Query(alias="status")] = ListingStatus.OPEN,
) -> list[ListingRead]:
    listings = await _svc(current, session).list(
        type_=type_filter, practice_area=practice_area, query=q,
        status=status_filter, limit=page.limit, offset=page.offset,
    )
    return [ListingRead.model_validate(x) for x in listings]


@router.get(
    "/listings/mine",
    response_model=list[ListingRead],
    summary="My listings",
    dependencies=[require_permission("marketplace:read")],
)
async def my_listings(
    current: CurrentUserDep, session: TenantSessionDep
) -> list[ListingRead]:
    return [ListingRead.model_validate(x) for x in await _svc(current, session).my_listings()]


@router.get(
    "/listings/{listing_id}",
    response_model=ListingRead,
    summary="Listing detail",
    dependencies=[require_permission("marketplace:read")],
)
async def get_listing(
    listing_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> ListingRead:
    return ListingRead.model_validate(await _svc(current, session).get(listing_id))


@router.post(
    "/listings/{listing_id}/close",
    response_model=ListingRead,
    summary="Close a listing",
    dependencies=[require_permission("marketplace:update")],
)
async def close_listing(
    listing_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> ListingRead:
    return ListingRead.model_validate(await _svc(current, session).close(listing_id))


@router.post(
    "/listings/{listing_id}/respond",
    response_model=ResponseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Respond to a listing",
    dependencies=[require_permission("marketplace:read")],
)
async def respond(
    listing_id: uuid.UUID,
    data: ResponseCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> ResponseRead:
    return ResponseRead.model_validate(await _svc(current, session).respond(listing_id, data))


@router.get(
    "/listings/{listing_id}/responses",
    response_model=list[ResponseRead],
    summary="Responses to a listing (poster only)",
    dependencies=[require_permission("marketplace:read")],
)
async def list_responses(
    listing_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> list[ResponseRead]:
    responses = await _svc(current, session).list_responses(listing_id)
    return [ResponseRead.model_validate(r) for r in responses]


@router.post(
    "/listings/{listing_id}/responses/{response_id}/accept", response_model=ListingRead,
    summary="Engage a responder on the linked matter",
    dependencies=[require_permission("marketplace:update"), require_permission("matter:update")],
)
async def accept_response(
    listing_id: uuid.UUID, response_id: uuid.UUID,
    current: CurrentUserDep, session: TenantSessionDep,
) -> ListingRead:
    return ListingRead.model_validate(await _svc(current, session).accept_response(listing_id, response_id))
