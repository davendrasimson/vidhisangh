"""CRM HTTP endpoints — leads, activities, pipeline, analytics (RBAC-guarded)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.modules.crm.models import LeadSource, LeadStatus
from app.modules.crm.schemas import (
    ActivityCreate,
    ActivityRead,
    LeadCreate,
    LeadDetail,
    LeadRead,
    LeadUpdate,
    PipelineColumn,
    SourceStat,
)
from app.modules.crm.service import CrmService

router = APIRouter(prefix="/crm", tags=["CRM"])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> CrmService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return CrmService(session, current.id, current.tenant_id)


# ─── Leads ──────────────────────────────────────────────────────────
@router.post(
    "/leads",
    response_model=LeadRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lead",
    dependencies=[require_permission("lead:create")],
)
async def create_lead(
    data: LeadCreate, current: CurrentUserDep, session: TenantSessionDep
) -> LeadRead:
    return LeadRead.model_validate(await _svc(current, session).create_lead(data))


@router.get(
    "/leads",
    response_model=list[LeadRead],
    summary="List leads",
    dependencies=[require_permission("lead:read")],
)
async def list_leads(
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
    status_filter: Annotated[LeadStatus | None, Query(alias="status")] = None,
    source: Annotated[LeadSource | None, Query()] = None,
) -> list[LeadRead]:
    leads = await _svc(current, session).list_leads(status_filter, source, page.limit, page.offset)
    return [LeadRead.model_validate(lead) for lead in leads]


@router.get(
    "/pipeline",
    response_model=list[PipelineColumn],
    summary="Pipeline board (leads grouped by stage)",
    dependencies=[require_permission("lead:read")],
)
async def pipeline(current: CurrentUserDep, session: TenantSessionDep) -> list[PipelineColumn]:
    return await _svc(current, session).pipeline()


@router.get(
    "/analytics/sources",
    response_model=list[SourceStat],
    summary="Lead source analytics (total & won per source)",
    dependencies=[require_permission("lead:read")],
)
async def source_analytics(
    current: CurrentUserDep, session: TenantSessionDep
) -> list[SourceStat]:
    return await _svc(current, session).source_analytics()


@router.get(
    "/leads/{lead_id}",
    response_model=LeadDetail,
    summary="Lead detail (with activities)",
    dependencies=[require_permission("lead:read")],
)
async def get_lead(
    lead_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> LeadDetail:
    return LeadDetail.model_validate(await _svc(current, session).get_lead(lead_id))


@router.patch(
    "/leads/{lead_id}",
    response_model=LeadRead,
    summary="Update a lead (stage, details)",
    dependencies=[require_permission("lead:update")],
)
async def update_lead(
    lead_id: uuid.UUID,
    data: LeadUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> LeadRead:
    return LeadRead.model_validate(await _svc(current, session).update_lead(lead_id, data))


@router.delete(
    "/leads/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a lead",
    dependencies=[require_permission("lead:delete")],
)
async def delete_lead(
    lead_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_lead(lead_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Activities ─────────────────────────────────────────────────────
@router.post(
    "/leads/{lead_id}/activities",
    response_model=ActivityRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log an activity / follow-up",
    dependencies=[require_permission("lead:update")],
)
async def add_activity(
    lead_id: uuid.UUID,
    data: ActivityCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> ActivityRead:
    return ActivityRead.model_validate(await _svc(current, session).add_activity(lead_id, data))


@router.post(
    "/activities/{activity_id}/complete",
    response_model=ActivityRead,
    summary="Mark a follow-up done / reopen",
    dependencies=[require_permission("lead:update")],
)
async def complete_activity(
    activity_id: uuid.UUID,
    current: CurrentUserDep,
    session: TenantSessionDep,
    done: Annotated[bool, Query()] = True,
) -> ActivityRead:
    return ActivityRead.model_validate(
        await _svc(current, session).complete_activity(activity_id, done)
    )


# ─── Convert ────────────────────────────────────────────────────────
@router.post(
    "/leads/{lead_id}/convert",
    status_code=status.HTTP_201_CREATED,
    summary="Convert a lead into a matter",
    dependencies=[require_permission("lead:update"), require_permission("matter:create")],
)
async def convert_lead(
    lead_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> dict:
    matter_id = await _svc(current, session).convert_to_matter(lead_id)
    return {"matter_id": str(matter_id)}
