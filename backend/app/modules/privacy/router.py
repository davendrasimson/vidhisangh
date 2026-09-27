"""Privacy HTTP endpoints.

``/privacy/notice`` is public (DPDP s.5 facts). ``/privacy/me/*`` act on the
signed-in user. ``/privacy/requests`` is the firm's rights-request register.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.modules.privacy.models import PrivacyRequestStatus
from app.modules.privacy.schemas import (
    PrivacyNoticeRead,
    PrivacyRequestCreate,
    PrivacyRequestRead,
    PrivacyRequestUpdate,
    UserDeleteRequest,
    UserDeleteResult,
)
from app.modules.privacy.service import RightsRequestService, UserPrivacyService, notice

router = APIRouter(prefix="/privacy", tags=["Privacy"])


def _tid(current: CurrentUserDep) -> uuid.UUID:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return current.tenant_id


@router.get("/notice", response_model=PrivacyNoticeRead, summary="Privacy notice facts (public): versions, grievance officer, retention")
async def privacy_notice() -> PrivacyNoticeRead:
    return PrivacyNoticeRead(**notice())


@router.get("/me/export", summary="Everything held about me, as a JSON download (DPDP s.11)")
async def export_me(current: CurrentUserDep, session: TenantSessionDep) -> JSONResponse:
    bundle = await UserPrivacyService(session, current.id, _tid(current)).export()
    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": f'attachment; filename="vidhisangh-{current.id}.json"'},
    )


@router.post("/me/delete", response_model=UserDeleteResult, summary="Erase my account (password confirmation; DPDP s.12)")
async def delete_me(data: UserDeleteRequest, current: CurrentUserDep, session: TenantSessionDep) -> UserDeleteResult:
    result = await UserPrivacyService(session, current.id, _tid(current)).erase(password=data.password, actor_label=current.email)
    return UserDeleteResult(**result)


# ═══ Rights requests (firm side) ════════════════════════════════════
@router.get("/requests", response_model=list[PrivacyRequestRead], summary="Rights requests received (access/correction/erasure/grievance)",
            dependencies=[require_permission("client:read")])
async def list_requests(
    current: CurrentUserDep, session: TenantSessionDep,
    status_: Annotated[PrivacyRequestStatus | None, Query(alias="status")] = None,
) -> list[PrivacyRequestRead]:
    svc = RightsRequestService(session, current.id, _tid(current))
    return [PrivacyRequestRead.model_validate(r) for r in await svc.list(status=status_)]


@router.post("/requests", response_model=PrivacyRequestRead, status_code=status.HTTP_201_CREATED,
             summary="Record a rights request received from a client", dependencies=[require_permission("client:update")])
async def create_request(data: PrivacyRequestCreate, current: CurrentUserDep, session: TenantSessionDep) -> PrivacyRequestRead:
    svc = RightsRequestService(session, current.id, _tid(current))
    return PrivacyRequestRead.model_validate(await svc.create(data, actor_label=current.email))


@router.get("/requests/{request_id}", response_model=PrivacyRequestRead, summary="One rights request",
            dependencies=[require_permission("client:read")])
async def get_request(request_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep) -> PrivacyRequestRead:
    return PrivacyRequestRead.model_validate(await RightsRequestService(session, current.id, _tid(current)).get(request_id))


@router.patch("/requests/{request_id}", response_model=PrivacyRequestRead, summary="Progress or close a rights request",
              dependencies=[require_permission("client:update")])
async def update_request(
    request_id: uuid.UUID, data: PrivacyRequestUpdate, current: CurrentUserDep, session: TenantSessionDep
) -> PrivacyRequestRead:
    svc = RightsRequestService(session, current.id, _tid(current))
    return PrivacyRequestRead.model_validate(await svc.update(request_id, data, actor_label=current.email))
