"""Pydantic schemas for API keys."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(min_length=1, max_length=100)
    # Required: keys must expire (at most 365 days out — enforced in the service).
    expires_at: datetime = Field(description="When the key stops working (max 365 days).")


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked: bool
    created_at: datetime


class ApiKeyCreated(ApiKeyRead):
    key: str  # the full plaintext key — shown only once at creation
