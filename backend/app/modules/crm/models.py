"""CRM domain models (Phase 5) — tenant-scoped with RLS."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import TenantScopedBase


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CONSULTATION = "consultation"
    WON = "won"
    LOST = "lost"


class LeadSource(StrEnum):
    REFERRAL = "referral"
    WEBSITE = "website"
    WALK_IN = "walk_in"
    CALL = "call"
    SOCIAL = "social"
    OTHER = "other"


class ActivityType(StrEnum):
    NOTE = "note"
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    CONSULTATION = "consultation"


class Lead(TenantScopedBase):
    __tablename__ = "leads"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source: Mapped[LeadSource] = mapped_column(
        String(20), default=LeadSource.OTHER, nullable=False, index=True
    )
    status: Mapped[LeadStatus] = mapped_column(
        String(20), default=LeadStatus.NEW, nullable=False, index=True
    )
    practice_area: Mapped[str | None] = mapped_column(String(150), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    referred_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    converted_matter_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    activities: Mapped[list["LeadActivity"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


class LeadActivity(TenantScopedBase):
    __tablename__ = "lead_activities"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[ActivityType] = mapped_column(
        String(20), default=ActivityType.NOTE, nullable=False
    )
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)  # follow-up date
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    lead: Mapped[Lead] = relationship(back_populates="activities")
