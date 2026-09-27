"""Subscription plan HTTP endpoints.

The plan catalog and current subscription are readable with ``tenant:read``
(every internal role); changing the plan requires ``tenant:manage``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.modules.audit.service import record_audit
from app.modules.plans.schemas import PlanRead, SubscriptionRead, SubscriptionUpdate
from app.modules.plans.service import PlansService

router = APIRouter(tags=["Plans"])


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> PlansService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return PlansService(session, current.tenant_id)


@router.get(
    "/admin/plans",
    response_model=list[PlanRead],
    summary="Available subscription plans",
    dependencies=[require_permission("tenant:read")],
)
async def list_plans(current: CurrentUserDep, session: TenantSessionDep) -> list[PlanRead]:
    return [PlanRead(**p) for p in await _svc(current, session).list_plans()]


@router.get(
    "/admin/subscription",
    response_model=SubscriptionRead,
    summary="Current subscription + usage",
    dependencies=[require_permission("tenant:read")],
)
async def get_subscription(current: CurrentUserDep, session: TenantSessionDep) -> SubscriptionRead:
    return SubscriptionRead(**await _svc(current, session).get_subscription())


@router.put(
    "/admin/subscription",
    response_model=SubscriptionRead,
    summary="Change subscription plan",
    dependencies=[require_permission("tenant:manage")],
)
async def change_plan(
    payload: SubscriptionUpdate, current: CurrentUserDep, session: TenantSessionDep
) -> SubscriptionRead:
    result = await _svc(current, session).change_plan(payload.tier)
    record_audit(
        session,
        tenant_id=current.tenant_id,
        actor_id=current.id,
        actor_label=current.email,
        action="subscription.changed",
        summary=f"Subscription changed to the {payload.tier.value} plan",
        entity_type="subscription",
        entity_id=payload.tier.value,
    )
    return SubscriptionRead(**result)
