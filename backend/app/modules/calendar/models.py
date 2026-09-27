"""Calendar domain model (Phase 3) — tenant-scoped with RLS."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import TenantScopedBase


class EventType(StrEnum):
    MEETING = "meeting"
    COURT = "court"
    APPOINTMENT = "appointment"
    REMINDER = "reminder"
    OTHER = "other"


class CalendarEvent(TenantScopedBase):
    __tablename__ = "calendar_events"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[EventType] = mapped_column(
        String(20), default=EventType.MEETING, nullable=False
    )
    # timestamptz, matching the database. A bare `datetime` mapping declares
    # the bind as naive `timestamp`, so an offset-aware value from the API
    # ("…T18:30:00Z") fails inside asyncpg with "can't subtract offset-naive
    # and offset-aware datetimes" — every agenda request 500'd on production.
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("matters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
