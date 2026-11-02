"""Notifications HTTP endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUserDep, TenantSessionDep, client_ip, require_permission
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

# Every route acts on the caller's *own* notifications/preferences; the single
# ``notification:read`` code (held by every role incl. externals) gates them all.
router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
    dependencies=[require_permission("notification:read")],
)

Pagination = Annotated[PageParams, Depends(page_params)]


class DailyOrdersPreference(BaseModel):
    enabled: bool
    email_verified: bool = False


class DailyOrdersUpdate(BaseModel):
    enabled: bool


@router.get("/daily-orders", response_model=DailyOrdersPreference)
async def get_daily_orders(
    current: CurrentUserDep, session: TenantSessionDep,
) -> DailyOrdersPreference:
    from app.modules.identity.models import User
    from app.modules.research.daily_orders import subscription

    row = await subscription(session, current.id)
    user = await session.get(User, current.id)
    return DailyOrdersPreference(
        enabled=bool(row and row.enabled),
        email_verified=bool(user and user.email and user.is_email_verified),
    )


@router.put("/daily-orders", response_model=DailyOrdersPreference)
async def set_daily_orders(
    data: DailyOrdersUpdate, current: CurrentUserDep, session: TenantSessionDep,
) -> DailyOrdersPreference:
    from app.modules.research.daily_orders import subscribe

    try:
        await subscribe(session, current.id, data.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await get_daily_orders(current, session)


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


class WhatsAppUpdatesRead(BaseModel):
    status: Literal["granted", "refused", "unasked"]
    # A verified mobile number is needed to receive them.
    phone_verified: bool


class WhatsAppUpdatesUpdate(BaseModel):
    granted: bool
    source: Literal["settings", "home"] = "settings"


async def _whatsapp_updates(current: CurrentUserDep, session: TenantSessionDep) -> WhatsAppUpdatesRead:
    from app.modules.identity.repository import UserRepository
    from app.modules.notifications.whatsapp_updates import choice_of

    user = await UserRepository(session).get_for_tenant(current.tenant_id, current.id)
    return WhatsAppUpdatesRead(
        status=await choice_of(session, current.id),
        phone_verified=bool(user and user.phone and user.is_phone_verified),
    )


@router.get("/whatsapp-updates", response_model=WhatsAppUpdatesRead, summary="Do I get product updates on WhatsApp?")
async def get_whatsapp_updates(current: CurrentUserDep, session: TenantSessionDep) -> WhatsAppUpdatesRead:
    return await _whatsapp_updates(current, session)


@router.put("/whatsapp-updates", response_model=WhatsAppUpdatesRead, summary="Say yes or no to product updates on WhatsApp")
async def set_whatsapp_updates(
    data: WhatsAppUpdatesUpdate, request: Request, current: CurrentUserDep, session: TenantSessionDep,
) -> WhatsAppUpdatesRead:
    """Each answer is a new row in the consent ledger (withdrawal never erases a grant)."""
    from app.modules.notifications.whatsapp_updates import record_choice

    await record_choice(session, current.id, data.granted, data.source, client_ip(request))
    return await _whatsapp_updates(current, session)


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


class PushDeviceIn(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    platform: Literal["android", "ios"]


@router.post("/devices", status_code=status.HTTP_204_NO_CONTENT, summary="Register this phone for push notifications")
async def register_device(data: PushDeviceIn, current: CurrentUserDep, session: TenantSessionDep) -> Response:
    """Called by the app after sign-in. A token already registered moves to
    whoever signed in on that phone last."""
    from sqlalchemy import select

    from app.modules.notifications.models import PushDevice

    device = await session.scalar(select(PushDevice).where(PushDevice.token == data.token))
    if device is None:
        session.add(PushDevice(user_id=current.id, token=data.token, platform=data.platform))
    else:
        device.user_id, device.platform = current.id, data.platform
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/devices/remove", status_code=status.HTTP_204_NO_CONTENT, summary="Stop push to this phone (sign-out)")
async def remove_device(data: PushDeviceIn, current: CurrentUserDep, session: TenantSessionDep) -> Response:
    from sqlalchemy import delete

    from app.modules.notifications.models import PushDevice

    await session.execute(delete(PushDevice).where(PushDevice.token == data.token, PushDevice.user_id == current.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
