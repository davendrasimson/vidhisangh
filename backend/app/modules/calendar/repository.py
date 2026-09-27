"""Data-access layer for the calendar. Reads own events plus matter hearings and
task deadlines (joined to their matter) for the unified agenda. Filters by
``tenant_id`` explicitly alongside RLS."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calendar.models import CalendarEvent
from app.modules.matters.models import (
    Hearing,
    Matter,
    MatterStatus,
    MatterTask,
    TaskStatus,
)


class CalendarRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, obj: object) -> None:
        self.session.add(obj)

    async def delete(self, obj: object) -> None:
        await self.session.delete(obj)

    async def get_event(
        self, tenant_id: uuid.UUID, event_id: uuid.UUID
    ) -> CalendarEvent | None:
        res = await self.session.execute(
            select(CalendarEvent).where(
                CalendarEvent.id == event_id,
                CalendarEvent.tenant_id == tenant_id,
                CalendarEvent.deleted_at.is_(None),
            )
        )
        return res.scalar_one_or_none()

    async def events_in_range(
        self, tenant_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        res = await self.session.execute(
            select(CalendarEvent)
            .where(
                CalendarEvent.tenant_id == tenant_id,
                CalendarEvent.deleted_at.is_(None),
                CalendarEvent.start_at >= start,
                CalendarEvent.start_at <= end,
            )
            .order_by(CalendarEvent.start_at)
        )
        return list(res.scalars().all())

    async def hearings_in_range(
        self, tenant_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[tuple[Hearing, str, str]]:
        res = await self.session.execute(
            select(Hearing, Matter.matter_number, Matter.title)
            .join(Matter, Matter.id == Hearing.matter_id)
            .where(
                Hearing.tenant_id == tenant_id,
                Hearing.deleted_at.is_(None),
                Hearing.scheduled_on >= start,
                Hearing.scheduled_on <= end,
            )
        )
        return [(row[0], row[1], row[2]) for row in res.all()]

    async def tasks_due_in_range(
        self, tenant_id: uuid.UUID, start: date, end: date
    ) -> list[tuple[MatterTask, str]]:
        res = await self.session.execute(
            select(MatterTask, Matter.matter_number)
            .join(Matter, Matter.id == MatterTask.matter_id)
            .where(
                MatterTask.tenant_id == tenant_id,
                MatterTask.deleted_at.is_(None),
                MatterTask.status == TaskStatus.OPEN,
                MatterTask.due_on.is_not(None),
                MatterTask.due_on >= start,
                MatterTask.due_on <= end,
            )
        )
        return [(row[0], row[1]) for row in res.all()]

    async def limitations_in_range(
        self, tenant_id: uuid.UUID, start: date, end: date
    ) -> list[Matter]:
        res = await self.session.execute(
            select(Matter).where(
                Matter.tenant_id == tenant_id,
                Matter.deleted_at.is_(None),
                Matter.status != MatterStatus.CLOSED,
                Matter.limitation_date.is_not(None),
                Matter.limitation_date >= start,
                Matter.limitation_date <= end,
            )
        )
        return list(res.scalars().all())
