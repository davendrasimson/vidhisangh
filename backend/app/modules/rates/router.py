"""Counsel rate card endpoints — `/rates`."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.modules.rates.schemas import RateCardRead, RateCreate, RateRead, RateUpdate
from app.modules.rates.service import RateService

router = APIRouter(prefix="/rates", tags=["Counsel rates"])


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> RateService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return RateService(session, current.id, current.tenant_id)


@router.get("/cards", response_model=list[RateCardRead], summary="Everyone's rate card",
            dependencies=[require_permission("matter:read")])
async def rate_cards(current: CurrentUserDep, session: TenantSessionDep) -> list[RateCardRead]:
    return await _svc(current, session).cards()


@router.post("", response_model=RateRead, status_code=status.HTTP_201_CREATED, summary="Add a rate",
             dependencies=[require_permission("billing:manage")])
async def create_rate(data: RateCreate, current: CurrentUserDep, session: TenantSessionDep) -> RateRead:
    return await _svc(current, session).create(data)


@router.patch("/{rate_id}", response_model=RateRead, summary="Edit a rate",
              dependencies=[require_permission("billing:manage")])
async def update_rate(rate_id: uuid.UUID, data: RateUpdate, current: CurrentUserDep, session: TenantSessionDep) -> RateRead:
    return await _svc(current, session).update(rate_id, data)


@router.delete("/{rate_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a rate",
               dependencies=[require_permission("billing:manage")])
async def delete_rate(rate_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep) -> Response:
    await _svc(current, session).delete(rate_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
