"""Pydantic schemas for the webhooks module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class EventTypeRead(BaseModel):
    key: str
    description: str


class WebhookCreate(BaseModel):
    url: HttpUrl
    description: str | None = Field(default=None, max_length=200)
    event_types: list[str] = Field(min_length=1, max_length=50)


class WebhookUpdate(BaseModel):
    url: HttpUrl | None = None
    description: str | None = Field(default=None, max_length=200)
    event_types: list[str] | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class WebhookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    url: str
    description: str | None
    event_types: list[str]
    is_active: bool
    consecutive_failures: int = 0
    auto_disabled_at: datetime | None = None
    created_at: datetime


class WebhookCreated(WebhookRead):
    secret: str  # returned once on creation so the receiver can verify signatures


class DeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    endpoint_id: uuid.UUID
    event_type: str
    status: str
    status_code: int | None
    detail: str | None  # fixed reason only; never the receiver's response body
    created_at: datetime
