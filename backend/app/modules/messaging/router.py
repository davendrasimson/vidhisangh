"""Messaging HTTP endpoints: conversations, messages, read-tracking."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import TenantError
from app.core.pagination import PageParams, page_params
from app.modules.messaging.models import Conversation
from app.modules.messaging.schemas import (
    ConversationRead,
    GroupConversationCreate,
    MessageCreate,
    MessageRead,
)
from app.modules.messaging.service import MessagingService

router = APIRouter(prefix="/conversations", tags=["Messaging"])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> MessagingService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return MessagingService(session, current.id, current.tenant_id)


def _read(conversation: Conversation, unread: int = 0) -> ConversationRead:
    out = ConversationRead.model_validate(conversation)
    out.unread_count = unread
    return out


# ─── Conversations ──────────────────────────────────────────────────
@router.post(
    "/direct/{user_id}",
    dependencies=[require_permission("message:send")],
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start (or open) a 1:1 conversation",
)
async def start_direct(
    user_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> ConversationRead:
    conversation = await _svc(current, session).start_direct(user_id)
    return _read(conversation)


@router.post(
    "/group",
    dependencies=[require_permission("message:send")],
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a group conversation",
)
async def create_group(
    data: GroupConversationCreate, current: CurrentUserDep, session: TenantSessionDep
) -> ConversationRead:
    conversation = await _svc(current, session).create_group(data)
    return _read(conversation)


@router.get("", dependencies=[require_permission("message:read")], response_model=list[ConversationRead], summary="My conversations")
async def list_conversations(
    current: CurrentUserDep, session: TenantSessionDep
) -> list[ConversationRead]:
    rows = await _svc(current, session).list_conversations()
    return [_read(conversation, unread) for conversation, unread in rows]


@router.get("/{conversation_id}", dependencies=[require_permission("message:read")], response_model=ConversationRead, summary="Get a conversation")
async def get_conversation(
    conversation_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> ConversationRead:
    conversation = await _svc(current, session).get_conversation(conversation_id)
    return _read(conversation)


# ─── Messages ───────────────────────────────────────────────────────
@router.get(
    "/{conversation_id}/messages",
    dependencies=[require_permission("message:read")],
    response_model=list[MessageRead],
    summary="List messages (marks the thread read)",
)
async def list_messages(
    conversation_id: uuid.UUID,
    page: Pagination,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> list[MessageRead]:
    messages = await _svc(current, session).list_messages(
        conversation_id, page.limit, page.offset
    )
    return [MessageRead.model_validate(m) for m in messages]


@router.post(
    "/{conversation_id}/messages",
    dependencies=[require_permission("message:send")],
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message",
)
async def send_message(
    conversation_id: uuid.UUID,
    data: MessageCreate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> MessageRead:
    message = await _svc(current, session).send_message(conversation_id, data)
    return MessageRead.model_validate(message)


@router.post(
    "/{conversation_id}/read",
    dependencies=[require_permission("message:read")],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark a conversation as read",
)
async def mark_read(
    conversation_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).mark_read(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/leave",
    dependencies=[require_permission("message:read")],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Leave a group conversation",
)
async def leave(
    conversation_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).leave(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
