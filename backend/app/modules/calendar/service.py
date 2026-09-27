"""Calendar service — events plus a unified agenda over events/hearings/deadlines."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.calendar.models import CalendarEvent
from app.modules.calendar.repository import CalendarRepository
from app.modules.calendar.schemas import AgendaItem, EventCreate, EventUpdate
from app.modules.tenancy.lookup import require_tenant_matter, require_tenant_user


def _sort_key(item: AgendaItem) -> datetime:
    # Compare naive vs aware datetimes uniformly (SQLite returns naive, PG aware).
    return item.start_at.replace(tzinfo=None)


class CalendarService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = CalendarRepository(session)

    # ── Events ──────────────────────────────────────────────────────
    async def _validate_refs(self, matter_id: uuid.UUID | None, assigned_to: uuid.UUID | None) -> None:
        """Referenced matter / person must belong to this tenant (audit A-32)."""
        if matter_id is not None:
            await require_tenant_matter(self.session, self.tenant_id, matter_id)
        if assigned_to is not None:
            await require_tenant_user(self.session, self.tenant_id, assigned_to)

    async def create_event(self, data: EventCreate) -> CalendarEvent:
        await self._validate_refs(data.matter_id, data.assigned_to)
        event = CalendarEvent(
            tenant_id=self.tenant_id,
            title=data.title,
            description=data.description,
            event_type=data.event_type,
            start_at=data.start_at,
            end_at=data.end_at,
            all_day=data.all_day,
            location=data.location,
            matter_id=data.matter_id,
            assigned_to=data.assigned_to,
            created_by=self.user_id,
        )
        self.repo.add(event)
        await self.session.flush()
        return event

    async def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        return await self.repo.events_in_range(self.tenant_id, start, end)

    async def update_event(self, event_id: uuid.UUID, data: EventUpdate) -> CalendarEvent:
        event = await self.repo.get_event(self.tenant_id, event_id)
        if event is None:
            raise NotFoundError("Event not found.")
        values = data.model_dump(exclude_unset=True)
        await self._validate_refs(values.get("matter_id"), values.get("assigned_to"))
        for field, value in values.items():
            setattr(event, field, value)
        return event

    async def delete_event(self, event_id: uuid.UUID) -> None:
        event = await self.repo.get_event(self.tenant_id, event_id)
        if event is None:
            raise NotFoundError("Event not found.")
        event.deleted_at = datetime.now(UTC)

    # ── Agenda ──────────────────────────────────────────────────────
    async def agenda(self, start: datetime, end: datetime) -> list[AgendaItem]:
        items: list[AgendaItem] = []

        for event in await self.repo.events_in_range(self.tenant_id, start, end):
            items.append(
                AgendaItem(
                    kind="event",
                    id=event.id,
                    title=event.title,
                    start_at=event.start_at,
                    end_at=event.end_at,
                    all_day=event.all_day,
                    event_type=str(event.event_type),
                    location=event.location,
                    matter_id=event.matter_id,
                )
            )

        for hearing, matter_number, matter_title in await self.repo.hearings_in_range(
            self.tenant_id, start, end
        ):
            items.append(
                AgendaItem(
                    kind="hearing",
                    id=hearing.id,
                    title=f"{matter_title} — {hearing.purpose or 'Hearing'}",
                    start_at=hearing.scheduled_on,
                    event_type="court",
                    status=str(hearing.status),
                    location=hearing.court,
                    matter_id=hearing.matter_id,
                    matter_number=matter_number,
                )
            )

        for task, matter_number in await self.repo.tasks_due_in_range(
            self.tenant_id, start.date(), end.date()
        ):
            assert task.due_on is not None  # filtered in the query
            items.append(
                AgendaItem(
                    kind="deadline",
                    id=task.id,
                    title=task.title,
                    start_at=datetime.combine(task.due_on, time.min),
                    all_day=True,
                    event_type="deadline",
                    status="open",
                    matter_id=task.matter_id,
                    matter_number=matter_number,
                )
            )

        for matter in await self.repo.limitations_in_range(
            self.tenant_id, start.date(), end.date()
        ):
            assert matter.limitation_date is not None  # filtered in the query
            items.append(
                AgendaItem(
                    kind="limitation",
                    id=matter.id,
                    title=f"Limitation: {matter.title}",
                    start_at=datetime.combine(matter.limitation_date, time.min),
                    all_day=True,
                    event_type="limitation",
                    status=str(matter.status),
                    matter_id=matter.id,
                    matter_number=matter.matter_number,
                )
            )

        items.sort(key=_sort_key)
        return items
