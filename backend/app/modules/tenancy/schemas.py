"""Pydantic schemas for the tenancy module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.tenancy.models import PlanTier, TenantStatus, TenantType


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    type: TenantType
    status: TenantStatus
    plan: PlanTier
    region: str
    created_at: datetime


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    type: TenantType | None = None
    primary_contact_email: str | None = None
    settings: dict | None = None
