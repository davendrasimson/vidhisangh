"""Pydantic schemas for subscription plans."""

from __future__ import annotations

from pydantic import BaseModel

from app.modules.tenancy.models import PlanTier, TenantStatus


class PlanRead(BaseModel):
    tier: PlanTier
    name: str
    price_inr: int | None  # None = custom / contact sales
    max_users: int | None  # None = unlimited
    max_matters: int | None
    storage_gb: int | None
    features: list[str]
    is_current: bool = False


class Usage(BaseModel):
    users: int
    matters: int


class SubscriptionRead(BaseModel):
    plan: PlanRead
    status: TenantStatus
    usage: Usage


class SubscriptionUpdate(BaseModel):
    tier: PlanTier
