"""Audit log HTTP endpoints (read-only, RBAC-guarded)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.modules.audit.schemas import AuditEventRead, ChainStatus
from app.modules.audit.service import AuditService

router = APIRouter(tags=["Audit"])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> AuditService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return AuditService(session, current.tenant_id)


@router.get(
    "/admin/audit",
    response_model=list[AuditEventRead],
    summary="Audit log",
    dependencies=[require_permission("audit:read")],
)
async def list_audit(
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
    action: Annotated[str | None, Query(description="Filter by action")] = None,
) -> list[AuditEventRead]:
    events = await _svc(current, session).list(action=action, limit=page.limit, offset=page.offset)
    return [AuditEventRead.model_validate(e) for e in events]


@router.get(
    "/admin/audit/verify",
    response_model=ChainStatus,
    summary="Verify the audit log's hash chain",
    dependencies=[require_permission("audit:read")],
)
async def verify_audit(current: CurrentUserDep, session: TenantSessionDep) -> ChainStatus:
    ok, bad = await _svc(current, session).verify()
    return ChainStatus(ok=ok, first_broken_id=bad)
