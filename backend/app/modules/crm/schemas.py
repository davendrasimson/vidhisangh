"""Pydantic schemas for the CRM module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.crm.models import ActivityType, LeadSource, LeadStatus


# ─── Leads ──────────────────────────────────────────────────────────
class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=30)
    source: LeadSource = LeadSource.OTHER
    practice_area: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=5000)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    referred_by: str | None = Field(default=None, max_length=200)
    assigned_to: uuid.UUID | None = None


class LeadUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=30)
    source: LeadSource | None = None
    status: LeadStatus | None = None
    practice_area: str | None = Field(default=None, max_length=150)
    notes: str | None = Field(default=None, max_length=5000)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    referred_by: str | None = Field(default=None, max_length=200)
    assigned_to: uuid.UUID | None = None


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    source: LeadSource
    status: LeadStatus
    practice_area: str | None
    notes: str | None
    estimated_value: Decimal | None
    referred_by: str | None
    assigned_to: uuid.UUID | None
    converted_matter_id: uuid.UUID | None
    client_id: uuid.UUID | None
    created_at: datetime


# ─── Activities ─────────────────────────────────────────────────────
class ActivityCreate(BaseModel):
    type: ActivityType = ActivityType.NOTE
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=5000)
    due_on: date | None = None


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    lead_id: uuid.UUID
    type: ActivityType
    subject: str | None
    body: str | None
    due_on: date | None
    completed: bool
    completed_at: datetime | None
    created_at: datetime


class LeadDetail(LeadRead):
    activities: list[ActivityRead] = Field(default_factory=list)


# ─── Pipeline & analytics ───────────────────────────────────────────
class PipelineColumn(BaseModel):
    status: LeadStatus
    count: int
    value: Decimal
    leads: list[LeadRead]


class SourceStat(BaseModel):
    source: LeadSource
    total: int
    won: int
