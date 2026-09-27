"""Pydantic schemas for the audit module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_label: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    summary: str
    meta: dict | None
    entry_hash: str | None = None
    created_at: datetime


class ChainStatus(BaseModel):
    ok: bool
    first_broken_id: uuid.UUID | None = None
