"""Pydantic schemas for the notifications module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.notifications.models import (
    DeliveryStatus,
    NotificationChannel,
    NotificationType,
)


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: NotificationType
    actor_id: uuid.UUID | None
    actor_name: str | None
    message: str
    link: str | None
    is_read: bool
    created_at: datetime


class UnreadCount(BaseModel):
    count: int


class ChannelPreference(BaseModel):
    channel: NotificationChannel
    enabled: bool
    types: list[str] = Field(default_factory=list)


class ChannelPreferenceUpdate(BaseModel):
    enabled: bool
    types: list[str] = Field(default_factory=list)


class DeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: NotificationType
    channel: NotificationChannel
    status: DeliveryStatus
    detail: str | None
    created_at: datetime
