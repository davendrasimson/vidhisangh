"""Pydantic schemas for the marketplace module."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.marketplace.models import ListingStatus, ListingType


class ListingCreate(BaseModel):
    type: ListingType = ListingType.REFERRAL
    title: str = Field(min_length=2, max_length=300)
    description: str = Field(min_length=1, max_length=8000)
    practice_area: str | None = Field(default=None, max_length=150)
    location: str | None = Field(default=None, max_length=200)
    budget: Decimal | None = Field(default=None, ge=0)
    matter_id: uuid.UUID | None = None


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: ListingType
    title: str
    description: str
    practice_area: str | None
    location: str | None
    budget: Decimal | None
    status: ListingStatus
    posted_by: uuid.UUID
    poster_name: str
    response_count: int
    matter_id: uuid.UUID | None
    accepted_response_id: uuid.UUID | None
    created_at: datetime


class ResponseCreate(BaseModel):
    message: str = Field(min_length=1, max_length=3000)


class ResponseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    listing_id: uuid.UUID
    responder_id: uuid.UUID
    responder_name: str
    responder_email: str | None
    message: str
    created_at: datetime
