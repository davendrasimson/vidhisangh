"""Pydantic schemas for the messaging module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.messaging.models import ConversationType


# ─── Participants ───────────────────────────────────────────────────
class ParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: uuid.UUID
    participant_name: str
    participant_avatar_url: str | None


# ─── Conversations ──────────────────────────────────────────────────
class GroupConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    participant_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: ConversationType
    title: str | None
    created_by: uuid.UUID
    last_message_at: datetime | None
    last_message_preview: str | None
    created_at: datetime

    participants: list[ParticipantRead] = Field(default_factory=list)
    unread_count: int = 0


# ─── Messages ───────────────────────────────────────────────────────
class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    sender_name: str
    sender_avatar_url: str | None
    body: str
    created_at: datetime
