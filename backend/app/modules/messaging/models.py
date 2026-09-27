"""Messaging domain models (Phase 2) — global cross-tenant chat layer."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import AuditedBase


class ConversationType(StrEnum):
    DIRECT = "direct"   # 1:1
    GROUP = "group"


class Conversation(AuditedBase):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("direct_key", name="conversation_direct_key"),
    )

    type: Mapped[ConversationType] = mapped_column(
        String(20), default=ConversationType.DIRECT, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    # Canonical "min:max" user-id pair for a direct chat (unique); null for groups.
    direct_key: Mapped[str | None] = mapped_column(String(120), nullable=True)

    last_message_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(200), nullable=True)

    participants: Mapped[list["ConversationParticipant"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class ConversationParticipant(AuditedBase):
    __tablename__ = "conversation_participants"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="participant_unique"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    # Denormalised participant snapshot.
    participant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    participant_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # When the participant last read the conversation (for unread counts).
    last_read_at: Mapped[datetime | None] = mapped_column(nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="participants")


class Message(AuditedBase):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    sender_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sender_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
