"""Data-access layer for messaging (global tables)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.messaging.models import (
    Conversation,
    ConversationParticipant,
    Message,
)


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, conversation: Conversation) -> None:
        self.session.add(conversation)

    async def get(self, conversation_id: uuid.UUID) -> Conversation | None:
        res = await self.session.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.deleted_at.is_(None))
            .options(selectinload(Conversation.participants))
        )
        return res.scalar_one_or_none()

    async def get_by_direct_key(self, direct_key: str) -> Conversation | None:
        res = await self.session.execute(
            select(Conversation)
            .where(
                Conversation.direct_key == direct_key,
                Conversation.deleted_at.is_(None),
            )
            .options(selectinload(Conversation.participants))
        )
        return res.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[Conversation]:
        recency = func.coalesce(Conversation.last_message_at, Conversation.created_at)
        res = await self.session.execute(
            select(Conversation)
            .join(
                ConversationParticipant,
                ConversationParticipant.conversation_id == Conversation.id,
            )
            .where(
                ConversationParticipant.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
            .options(selectinload(Conversation.participants))
            .order_by(recency.desc())
        )
        return list(res.scalars().all())


class ParticipantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, participant: ConversationParticipant) -> None:
        self.session.add(participant)

    async def delete(self, participant: ConversationParticipant) -> None:
        await self.session.delete(participant)

    async def get(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> ConversationParticipant | None:
        res = await self.session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
        return res.scalar_one_or_none()


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, message: Message) -> None:
        self.session.add(message)

    async def list_for_conversation(
        self, conversation_id: uuid.UUID, limit: int, offset: int
    ) -> list[Message]:
        # Most recent `limit` messages, returned oldest→newest for display.
        res = await self.session.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.deleted_at.is_(None),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(reversed(res.scalars().all()))

    async def unread_count(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        last_read_at: datetime | None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.deleted_at.is_(None),
                Message.sender_id != user_id,
            )
        )
        if last_read_at is not None:
            stmt = stmt.where(Message.created_at > last_read_at)
        res = await self.session.execute(stmt)
        return int(res.scalar_one())
