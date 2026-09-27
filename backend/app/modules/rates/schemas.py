"""Pydantic schemas for counsel rate cards."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.matters.models import RateBasis
from app.modules.matters.schemas import Money


class RateCreate(BaseModel):
    user_id: uuid.UUID
    basis: RateBasis
    amount: Decimal = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    effective_from: date | None = None   # defaults to today
    effective_to: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class RateUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, ge=0)
    effective_from: date | None = None
    effective_to: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class RateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str | None = None
    basis: RateBasis
    amount: Money
    currency: str
    effective_from: date
    effective_to: date | None
    notes: str | None
    created_at: datetime
    is_current: bool = True


class RateCardRead(BaseModel):
    """One person with their rates, for the settings screen."""

    user_id: uuid.UUID
    full_name: str
    email: str
    is_active: bool
    rates: list[RateRead] = Field(default_factory=list)
