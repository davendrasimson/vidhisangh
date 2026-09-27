"""Notifications HTTP endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep
from app.core.pagination import PageParams, page_params
from app.modules.notifications.models import NotificationChannel
from app.modules.notifications.schemas import (
    ChannelPreference,
    ChannelPreferenceUpdate,
    DeliveryRead,
    NotificationRead,
    UnreadCount,
)
from app.modules.notifications.service import NotificationService, PreferenceService

router = APIRouter(prefix="/notifications", tags=["Notifications"])

Pagination = Annotated[PageParams, Depends(page_params)]


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> NotificationService:
    return NotificationService(session, current.id)


def _prefs(current: CurrentUserDep, session: TenantSessionDep) -> PreferenceService:
    return PreferenceService(session, current.id)


@router.get("", response_model=list[NotificationRead], summary="My notifications")
async def list_notifications(
    page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[NotificationRead]:
    items = await _svc(current, session).list(page.limit, page.offset)
    return [NotificationRead.model_validate(n) for n in items]


@router.get("/unread-count", response_model=UnreadCount, summary="Unread notification count")
async def unread_count(current: CurrentUserDep, session: TenantSessionDep) -> UnreadCount:
    return UnreadCount(count=await _svc(current, session).unread_count())


@router.get(
    "/preferences",
    response_model=list[ChannelPreference],
    summary="My channel preferences (rule engine)",
)
async def list_preferences(
    current: CurrentUserDep, session: TenantSessionDep
) -> list[ChannelPreference]:
    return [ChannelPreference(**p) for p in await _prefs(current, session).list()]


@router.put(
    "/preferences/{channel}",
    response_model=ChannelPreference,
    summary="Enable/disable a channel (optionally scoped to types)",
)
async def update_preference(
    channel: NotificationChannel,
    payload: ChannelPreferenceUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> ChannelPreference:
    updated = await _prefs(current, session).update(channel, payload.enabled, payload.types)
    return ChannelPreference(**updated)


@router.get(
    "/deliveries",
    response_model=list[DeliveryRead],
    summary="My notification delivery log",
)
async def list_deliveries(
    page: Pagination, current: CurrentUserDep, session: TenantSessionDep
) -> list[DeliveryRead]:
    items = await _svc(current, session).deliveries(page.limit, page.offset)
    return [DeliveryRead.model_validate(d) for d in items]


@router.post(
    "/read-all", status_code=status.HTTP_204_NO_CONTENT, summary="Mark all as read"
)
async def mark_all_read(current: CurrentUserDep, session: TenantSessionDep) -> Response:
    await _svc(current, session).mark_all_read()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark a notification as read",
)
async def mark_read(
    notification_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).mark_read(notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
