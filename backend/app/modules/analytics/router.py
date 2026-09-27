"""Analytics HTTP endpoints — read-only practice dashboards (RBAC-guarded)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.modules.analytics.schemas import AnalyticsOverview
from app.modules.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> AnalyticsService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return AnalyticsService(session, current.tenant_id)


@router.get(
    "/overview",
    response_model=AnalyticsOverview,
    summary="Practice analytics overview",
    dependencies=[require_permission("analytics:view")],
)
async def overview(current: CurrentUserDep, session: TenantSessionDep) -> AnalyticsOverview:
    """Composite dashboard: revenue, caseload, CRM pipeline, productivity, and a
    6-month revenue trend — everything the analytics screen needs in one call."""
    return await _svc(current, session).overview(date.today())
