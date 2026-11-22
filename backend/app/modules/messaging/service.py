"""Messaging service — business logic for direct & group conversations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.network.blocks import is_blocked_either_way
from app.core.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.modules.messaging.models import (
    Conversation,
    ConversationParticipant,
    ConversationType,
    Message,
)
from app.modules.messaging.repository import (
    ConversationRepository,
    MessageRepository,
    ParticipantRepository,
)
from app.modules.messaging.realtime import manager
from app.modules.messaging.schemas import GroupConversationCreate, MessageCreate
from app.modules.network.repository import IdentityRepository


def _direct_key(a: uuid.UUID, b: uuid.UUID) -> str:
    return ":".join(sorted([str(a), str(b)]))


class MessagingService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.conversations = ConversationRepository(session)
        self.participants = ParticipantRepository(session)
        self.messages = MessageRepository(session)
        self.identities = IdentityRepository(session)

    # ── Helpers ─────────────────────────────────────────────────────
    def _participant(
        self, user_id: uuid.UUID, name: str, avatar: str | None
    ) -> ConversationParticipant:
        return ConversationParticipant(
            user_id=user_id, participant_name=name, participant_avatar_url=avatar
        )

    async def _reload(self, conversation_id: uuid.UUID) -> Conversation:
        """Re-fetch with participants eagerly loaded (for the response)."""
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:  # pragma: no cover - just-created row
            raise NotFoundError("Conversation not found.")
        return conversation

    async def _require_participant(
        self, conversation_id: uuid.UUID
    ) -> tuple[Conversation, ConversationParticipant]:
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        participant = await self.participants.get(conversation_id, self.user_id)
        if participant is None:
            raise PermissionDeniedError("You are not part of this conversation.")
        return conversation, participant

    # ── Conversations ───────────────────────────────────────────────
    async def start_direct(self, target_user_id: uuid.UUID) -> Conversation:
        if target_user_id == self.user_id:
            raise ValidationError("You cannot message yourself.")
        if await is_blocked_either_way(self.session, self.user_id, target_user_id):
            raise NotFoundError("That user is not discoverable on the network.")
        key = _direct_key(self.user_id, target_user_id)
        existing = await self.conversations.get_by_direct_key(key)
        if existing is not None:
            return existing

        identities = await self.identities.get_many([self.user_id, target_user_id])
        me = identities.get(self.user_id)
        them = identities.get(target_user_id)
        if me is None or them is None:
            raise NotFoundError("That user is not discoverable on the network.")

        conversation = Conversation(
            type=ConversationType.DIRECT,
            created_by=self.user_id,
            direct_key=key,
        )
        # Build the participant graph before the first flush so no lazy load of
        # the (empty) collection is triggered on a persistent object.
        conversation.participants = [
            self._participant(self.user_id, me.display_name, me.avatar_url),
            self._participant(target_user_id, them.display_name, them.avatar_url),
        ]
        self.conversations.add(conversation)
        await self.session.flush()
        return await self._reload(conversation.id)

    async def create_group(self, data: GroupConversationCreate) -> Conversation:
        ids = [uid for uid in dict.fromkeys(data.participant_ids) if uid != self.user_id]
        identities = await self.identities.get_many([self.user_id, *ids])
        me = identities.get(self.user_id)
        if me is None:
            raise NotFoundError("Your network identity is missing.")

        members = [self._participant(self.user_id, me.display_name, me.avatar_url)]
        for uid in ids:
            identity = identities.get(uid)
            if identity is not None:
                members.append(
                    self._participant(uid, identity.display_name, identity.avatar_url)
                )

        conversation = Conversation(
            type=ConversationType.GROUP,
            title=data.title,
            created_by=self.user_id,
        )
        conversation.participants = members
        self.conversations.add(conversation)
        await self.session.flush()
        return await self._reload(conversation.id)

    async def list_conversations(self) -> list[tuple[Conversation, int]]:
        conversations = await self.conversations.list_for_user(self.user_id)
        result: list[tuple[Conversation, int]] = []
        for conversation in conversations:
            mine = next(
                (p for p in conversation.participants if p.user_id == self.user_id), None
            )
            unread = await self.messages.unread_count(
                conversation.id, self.user_id, mine.last_read_at if mine else None
            )
            result.append((conversation, unread))
        return result

    async def get_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        conversation, _ = await self._require_participant(conversation_id)
        return conversation

    # ── Messages ────────────────────────────────────────────────────
    async def list_messages(
        self, conversation_id: uuid.UUID, limit: int, offset: int
    ) -> list[Message]:
        _conversation, participant = await self._require_participant(conversation_id)
        messages = await self.messages.list_for_conversation(conversation_id, limit, offset)
        participant.last_read_at = datetime.now(UTC)  # opening the thread marks it read
        return messages

    async def send_message(
        self, conversation_id: uuid.UUID, data: MessageCreate
    ) -> Message:
        conversation, participant = await self._require_participant(conversation_id)
        for other in conversation.participants:
            if other.user_id != self.user_id and await is_blocked_either_way(self.session, self.user_id, other.user_id):
                raise ValidationError("You cannot message this member.")
        me = await self.identities.get(self.user_id)
        name = me.display_name if me else "Unknown"
        avatar = me.avatar_url if me else None
        message = Message(
            conversation_id=conversation_id,
            sender_id=self.user_id,
            sender_name=name,
            sender_avatar_url=avatar,
            body=data.body,
        )
        self.messages.add(message)
        now = datetime.now(UTC)
        conversation.last_message_at = now
        conversation.last_message_preview = data.body[:200]
        participant.last_read_at = now  # the sender has read their own message
        await self.session.flush()

        # Live-deliver to any online recipients (no-op if none are connected).
        recipients = [
            p.user_id for p in conversation.participants if p.user_id != self.user_id
        ]
        online = manager.online_among(recipients)
        if online:
            await manager.send_to_users(
                online,
                {
                    "type": "message",
                    "conversation_id": str(conversation_id),
                    "message": {
                        "id": str(message.id),
                        "conversation_id": str(conversation_id),
                        "sender_id": str(self.user_id),
                        "sender_name": name,
                        "sender_avatar_url": avatar,
                        "body": message.body,
                        "created_at": message.created_at.isoformat(),
                    },
                },
            )
        return message

    async def mark_read(self, conversation_id: uuid.UUID) -> None:
        _conversation, participant = await self._require_participant(conversation_id)
        participant.last_read_at = datetime.now(UTC)

    async def leave(self, conversation_id: uuid.UUID) -> None:
        conversation, participant = await self._require_participant(conversation_id)
        if conversation.type == ConversationType.DIRECT:
            raise ValidationError("You cannot leave a direct conversation.")
        await self.participants.delete(participant)
