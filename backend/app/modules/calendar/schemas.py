"""Pydantic schemas for the calendar module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.calendar.models import EventType


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    event_type: EventType = EventType.MEETING
    start_at: datetime
    end_at: datetime | None = None
    all_day: bool = False
    location: str | None = Field(default=None, max_length=300)
    matter_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    event_type: EventType | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    location: str | None = Field(default=None, max_length=300)
    matter_id: uuid.UUID | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    description: str | None
    event_type: EventType
    start_at: datetime
    end_at: datetime | None
    all_day: bool
    location: str | None
    matter_id: uuid.UUID | None
    assigned_to: uuid.UUID | None
    created_at: datetime


class AgendaItem(BaseModel):
    """A unified calendar entry: a standalone event, a hearing, or a deadline."""

    kind: str  # event | hearing | deadline
    id: uuid.UUID
    title: str
    start_at: datetime
    end_at: datetime | None = None
    all_day: bool = False
    event_type: str | None = None
    status: str | None = None
    location: str | None = None
    matter_id: uuid.UUID | None = None
    matter_number: str | None = None
    # Hearings: court, courtroom and cause-list item (home screen, diary).
    court: str | None = None
    court_room: str | None = None
    item_number: str | None = None
