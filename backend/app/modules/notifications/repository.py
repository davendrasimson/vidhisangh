"""Data-access layer for notifications (global tables)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationPreference,
)


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, notification: Notification) -> None:
        self.session.add(notification)

    async def get(self, notification_id: uuid.UUID) -> Notification | None:
        res = await self.session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return res.scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int, offset: int
    ) -> list[Notification]:
        res = await self.session.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def unread_count(self, user_id: uuid.UUID) -> int:
        res = await self.session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        return int(res.scalar_one())

    async def mark_all_read(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )


class PreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, pref: NotificationPreference) -> None:
        self.session.add(pref)

    async def for_user(self, user_id: uuid.UUID) -> list[NotificationPreference]:
        res = await self.session.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )
        return list(res.scalars().all())

    async def get(
        self, user_id: uuid.UUID, channel: str
    ) -> NotificationPreference | None:
        res = await self.session.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.channel == channel,
            )
        )
        return res.scalar_one_or_none()


class DeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, delivery: NotificationDelivery) -> None:
        self.session.add(delivery)

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int, offset: int
    ) -> list[NotificationDelivery]:
        res = await self.session.execute(
            select(NotificationDelivery)
            .where(NotificationDelivery.user_id == user_id)
            .order_by(NotificationDelivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())
