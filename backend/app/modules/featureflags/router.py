"""Feature-flag HTTP endpoints.

Managing flags requires ``tenant:manage`` (org admins); the resolved on/off map
is readable by any authenticated tenant user so the app can gate features.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.modules.audit.service import record_audit
from app.modules.featureflags.schemas import FlagRead, FlagUpdate
from app.modules.featureflags.service import FeatureFlagService

router = APIRouter(tags=["Feature Flags"])


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> FeatureFlagService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return FeatureFlagService(session, current.id, current.tenant_id)


@router.get(
    "/admin/feature-flags",
    response_model=list[FlagRead],
    summary="List feature flags (catalog + tenant overrides)",
    dependencies=[require_permission("tenant:manage")],
)
async def list_flags(current: CurrentUserDep, session: TenantSessionDep) -> list[FlagRead]:
    return [FlagRead(**f) for f in await _svc(current, session).list_flags()]


@router.put(
    "/admin/feature-flags/{key}",
    response_model=FlagRead,
    summary="Enable/disable a feature flag for this tenant",
    dependencies=[require_permission("tenant:manage")],
)
async def set_flag(
    key: str, payload: FlagUpdate, current: CurrentUserDep, session: TenantSessionDep
) -> FlagRead:
    result = await _svc(current, session).set_flag(key, payload.enabled)
    record_audit(
        session,
        tenant_id=current.tenant_id,
        actor_id=current.id,
        actor_label=current.email,
        action="feature_flag.updated",
        summary=f"Feature '{key}' {'enabled' if payload.enabled else 'disabled'}",
        entity_type="feature_flag",
        entity_id=key,
    )
    return FlagRead(**result)


@router.get(
    "/feature-flags",
    response_model=dict[str, bool],
    summary="Resolved feature flags for the current tenant",
)
async def resolved_flags(current: CurrentUserDep, session: TenantSessionDep) -> dict[str, bool]:
    return await _svc(current, session).resolve()
