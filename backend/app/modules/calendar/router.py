"""Calendar HTTP endpoints — events + unified agenda (tenant-scoped)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.deps import CurrentUserDep, TenantSessionDep
from app.core.exceptions import TenantError
from app.modules.calendar.schemas import (
    AgendaItem,
    EventCreate,
    EventRead,
    EventUpdate,
)
from app.modules.calendar.service import CalendarService

router = APIRouter(prefix="/calendar", tags=["Calendar"])


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> CalendarService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return CalendarService(session, current.id, current.tenant_id)


@router.post(
    "/events",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a calendar event",
)
async def create_event(
    data: EventCreate, current: CurrentUserDep, session: TenantSessionDep
) -> EventRead:
    event = await _svc(current, session).create_event(data)
    return EventRead.model_validate(event)


@router.get("/events", response_model=list[EventRead], summary="Events in a date range")
async def list_events(
    current: CurrentUserDep,
    session: TenantSessionDep,
    start: Annotated[datetime, Query()],
    end: Annotated[datetime, Query()],
) -> list[EventRead]:
    events = await _svc(current, session).list_events(start, end)
    return [EventRead.model_validate(e) for e in events]


@router.get(
    "/agenda",
    response_model=list[AgendaItem],
    summary="Unified agenda: events + hearings + task deadlines",
)
async def agenda(
    current: CurrentUserDep,
    session: TenantSessionDep,
    start: Annotated[datetime, Query()],
    end: Annotated[datetime, Query()],
) -> list[AgendaItem]:
    return await _svc(current, session).agenda(start, end)


@router.patch("/events/{event_id}", response_model=EventRead, summary="Update an event")
async def update_event(
    event_id: uuid.UUID,
    data: EventUpdate,
    current: CurrentUserDep,
    session: TenantSessionDep,
) -> EventRead:
    event = await _svc(current, session).update_event(event_id, data)
    return EventRead.model_validate(event)


@router.delete(
    "/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an event",
)
async def delete_event(
    event_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_event(event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
