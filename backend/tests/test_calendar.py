"""Calendar module tests — events and the unified agenda over hearings/deadlines."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"
RANGE = {"start": "2026-07-01T00:00:00Z", "end": "2026-12-31T23:59:59Z"}


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
    resp = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": org,
            "full_name": f"Adv. {email.split('@')[0].title()}",
            "email": email,
            "password": pw,
            "accept_terms": True,
        },
    )
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    return headers, me


async def test_events_crud(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Cal LLP", "cal@firm.co", strong_password)

    created = await client.post(
        f"{API}/calendar/events",
        headers=h,
        json={"title": "Client meeting", "event_type": "meeting", "start_at": "2026-07-20T09:00:00Z"},
    )
    assert created.status_code == 201, created.text
    eid = created.json()["id"]

    listed = await client.get(f"{API}/calendar/events", headers=h, params=RANGE)
    assert [e["id"] for e in listed.json()] == [eid]

    upd = await client.patch(f"{API}/calendar/events/{eid}", headers=h, json={"location": "Chamber 3"})
    assert upd.json()["location"] == "Chamber 3"

    assert (await client.delete(f"{API}/calendar/events/{eid}", headers=h)).status_code == 204
    assert (await client.get(f"{API}/calendar/events", headers=h, params=RANGE)).json() == []


async def test_agenda_merges_events_hearings_deadlines(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Agenda LLP", "agenda@firm.co", strong_password)
    mid = (await client.post(f"{API}/matters", headers=h, json={"title": "Big case", "client_name": "C"})).json()["id"]

    # A hearing (Aug 1), a task deadline (Jul 25) and a standalone event (Jul 20).
    await client.post(
        f"{API}/matters/{mid}/hearings", headers=h,
        json={"scheduled_on": "2026-08-01T10:30:00Z", "purpose": "First hearing",
              "court": "Delhi High Court", "court_room": "12", "item_number": "34"},
    )
    await client.post(
        f"{API}/matters/{mid}/tasks", headers=h,
        json={"title": "File reply", "due_on": "2026-07-25"},
    )
    await client.post(
        f"{API}/calendar/events", headers=h,
        json={"title": "Strategy call", "start_at": "2026-07-20T09:00:00Z"},
    )

    agenda = await client.get(f"{API}/calendar/agenda", headers=h, params=RANGE)
    assert agenda.status_code == 200, agenda.text
    items = agenda.json()
    kinds = [i["kind"] for i in items]
    assert set(kinds) == {"event", "deadline", "hearing"}
    # Sorted chronologically: event (Jul 20) → deadline (Jul 25) → hearing (Aug 1).
    assert kinds == ["event", "deadline", "hearing"]
    hearing = next(i for i in items if i["kind"] == "hearing")
    assert hearing["matter_id"] == mid
    assert "Big case" in hearing["title"]
    assert (hearing["court"], hearing["court_room"], hearing["item_number"]) == ("Delhi High Court", "12", "34")


async def test_agenda_includes_limitation(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Lim LLP", "lim@firm.co", strong_password)
    await client.post(
        f"{API}/matters", headers=h,
        json={"title": "Urgent", "client_name": "C", "limitation_date": "2026-08-15"},
    )
    agenda = await client.get(f"{API}/calendar/agenda", headers=h, params=RANGE)
    lim = [i for i in agenda.json() if i["kind"] == "limitation"]
    assert len(lim) == 1
    assert "Urgent" in lim[0]["title"]


async def test_calendar_tenant_isolation(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _user(client, "Firm A", "cala@firma.co", strong_password)
    b_h, _ = await _user(client, "Firm B", "calb@firmb.co", strong_password)
    await client.post(
        f"{API}/calendar/events", headers=a_h,
        json={"title": "Private", "start_at": "2026-07-20T09:00:00Z"},
    )
    assert (await client.get(f"{API}/calendar/events", headers=b_h, params=RANGE)).json() == []
    assert (await client.get(f"{API}/calendar/agenda", headers=b_h, params=RANGE)).json() == []
