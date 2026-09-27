"""Tenancy domain models.

A ``Tenant`` is an isolated customer workspace — an individual advocate, a law
firm of any size, or a corporate legal department. It is a **global** table
(not itself tenant-scoped); every other tenant-owned row references it and is
isolated by row-level security.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import AuditedBase


class TenantType(StrEnum):
    INDIVIDUAL = "individual"
    SMALL_FIRM = "small_firm"
    LARGE_FIRM = "large_firm"
    ENTERPRISE = "enterprise"
    GOVERNMENT = "government"


class TenantStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class PlanTier(StrEnum):
    FREE = "free"
    SOLO = "solo"
    TEAM = "team"
    FIRM = "firm"
    ENTERPRISE = "enterprise"


class Tenant(AuditedBase):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    type: Mapped[TenantType] = mapped_column(
        String(32), nullable=False, default=TenantType.INDIVIDUAL
    )
    status: Mapped[TenantStatus] = mapped_column(
        String(32), nullable=False, default=TenantStatus.TRIAL, index=True
    )
    plan: Mapped[PlanTier] = mapped_column(
        String(32), nullable=False, default=PlanTier.FREE
    )
    # Data-residency region (e.g. ap-south-1) — supports future dedicated DBs.
    region: Mapped[str] = mapped_column(String(32), nullable=False, default="ap-south-1")
    primary_contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Free-form per-tenant configuration (feature flags, branding, limits).
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Offboarding (DPDP s.8(7)): when the owner cancelled, and when the
    # retention job may cascade-delete everything the tenant holds.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erase_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Tenant {self.slug} ({self.status})>"
