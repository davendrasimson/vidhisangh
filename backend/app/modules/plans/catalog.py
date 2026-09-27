"""The subscription plan catalog, keyed by :class:`PlanTier`.

Limits use ``None`` to mean *unlimited*; ``price_inr`` uses ``None`` to mean
*custom / contact sales*. Keep tiers aligned with ``PlanTier`` in the tenancy
model — every tier must appear here.
"""

from __future__ import annotations

from typing import NamedTuple

from app.modules.tenancy.models import PlanTier


class PlanDef(NamedTuple):
    tier: PlanTier
    name: str
    price_inr: int | None  # monthly, in rupees; None = custom
    max_users: int | None  # None = unlimited
    max_matters: int | None
    storage_gb: int | None
    features: list[str]


PLAN_CATALOG: list[PlanDef] = [
    PlanDef(
        PlanTier.FREE, "Free", 0, 1, 25, 1,
        ["Matters & documents", "Calendar & tasks", "In-app notifications"],
    ),
    PlanDef(
        PlanTier.SOLO, "Solo", 999, 1, 200, 10,
        ["Everything in Free", "CRM & billing", "Knowledge base", "Email notifications"],
    ),
    PlanDef(
        PlanTier.TEAM, "Team", 2999, 5, 1000, 50,
        ["Everything in Solo", "Analytics dashboards", "Marketplace", "Client portal"],
    ),
    PlanDef(
        PlanTier.FIRM, "Firm", 7999, 25, None, 250,
        ["Everything in Team", "Slack notifications", "Feature flags", "Priority support"],
    ),
    PlanDef(
        PlanTier.ENTERPRISE, "Enterprise", None, None, None, None,
        ["Everything in Firm", "SSO / OIDC", "Dedicated data region", "SLA & onboarding"],
    ),
]

CATALOG_BY_TIER: dict[PlanTier, PlanDef] = {p.tier: p for p in PLAN_CATALOG}
