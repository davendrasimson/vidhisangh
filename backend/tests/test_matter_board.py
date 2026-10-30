"""Matter board — open matters by stage with owner, next step and attention flags."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.test_matters import API, _user

pytestmark = pytest.mark.asyncio


def _iso(day: date, hour: int = 10) -> str:
    return datetime(day.year, day.month, day.day, hour, 30, tzinfo=UTC).isoformat()


async def test_board_groups_by_stage_with_next_step_and_flags(client: AsyncClient, strong_password: str) -> None:
    h, me = await _user(client, "Board LLP", "board@firm.co", strong_password)
    today = date.today()

    # A: hearing in 3 days, an overdue task, lead counsel set.
    a = (await client.post(f"{API}/matters", headers=h, json={
        "title": "A v. State", "client_name": "A", "stage": "evidence", "priority": "high",
        "lead_counsel_id": me["id"], "court": "Delhi High Court",
    })).json()
    await client.post(f"{API}/matters/{a['id']}/hearings", headers=h,
                      json={"scheduled_on": _iso(today + timedelta(days=3)), "court": "Court 12", "purpose": "Evidence of PW-1"})
    await client.post(f"{API}/matters/{a['id']}/tasks", headers=h,
                      json={"title": "File affidavit of evidence", "due_on": (today - timedelta(days=2)).isoformat()})
    await client.post(f"{API}/matters/{a['id']}/tasks", headers=h,
                      json={"title": "Prepare cross-examination", "due_on": (today + timedelta(days=10)).isoformat()})

    # B: nothing scheduled, no tasks, limitation in 10 days.
    b = (await client.post(f"{API}/matters", headers=h, json={
        "title": "B appeal", "client_name": "B", "stage": "filing",
        "limitation_date": (today + timedelta(days=10)).isoformat(),
    })).json()

    # C: closed — never on the board. D: on hold.
    c = (await client.post(f"{API}/matters", headers=h, json={"title": "C closed", "client_name": "C"})).json()
    await client.patch(f"{API}/matters/{c['id']}", headers=h, json={"status": "closed", "stage": "closed"})
    d = (await client.post(f"{API}/matters", headers=h, json={"title": "D on hold", "client_name": "D", "stage": "intake"})).json()
    await client.patch(f"{API}/matters/{d['id']}", headers=h, json={"status": "on_hold"})

    resp = await client.get(f"{API}/matters/board", headers=h)
    assert resp.status_code == 200, resp.text
    board = resp.json()
    assert [col["stage"] for col in board["columns"]] == ["intake", "filing", "pleadings", "evidence", "arguments", "judgment"]
    cards = {card["id"]: card for col in board["columns"] for card in col["matters"]}
    assert set(cards) == {a["id"], b["id"], d["id"]} and board["total"] == 3

    ca = cards[a["id"]]
    assert ca["owner_name"] == me["full_name"] and ca["owner_id"] == me["id"]
    assert ca["next_hearing_on"] == (today + timedelta(days=3)).isoformat()
    assert ca["next_hearing_court"] == "Court 12" and ca["next_hearing_purpose"] == "Evidence of PW-1"
    assert ca["next_task_title"] == "File affidavit of evidence"      # earliest due first
    assert ca["open_tasks"] == 2 and ca["overdue_tasks"] == 1
    assert ca["flags"] == ["hearing_soon", "overdue_task"]
    assert ca["days_idle"] == 0 and ca["last_activity_on"] == today.isoformat()

    cb = cards[b["id"]]
    assert cb["flags"] == ["limitation_soon", "no_next_step"] and cb["next_hearing_on"] is None
    assert cards[d["id"]]["flags"] == ["no_next_step", "on_hold"]

    assert board["attention"] == 3   # A: overdue task; B: limitation + no step; D: no step
    assert board["flag_counts"] == {"hearing_soon": 1, "overdue_task": 1, "limitation_soon": 1, "no_next_step": 2, "on_hold": 1}

    # Urgent cards come first inside a column.
    e = (await client.post(f"{API}/matters", headers=h, json={"title": "E urgent", "client_name": "E", "stage": "filing",
                                                              "limitation_date": (today - timedelta(days=1)).isoformat()})).json()
    board = (await client.get(f"{API}/matters/board", headers=h)).json()
    filing = next(col for col in board["columns"] if col["stage"] == "filing")
    assert [m["id"] for m in filing["matters"]] == [e["id"], b["id"]]
    assert filing["matters"][0]["flags"] == ["limitation_passed", "no_next_step"]


async def test_board_for_one_person_and_tenant_isolation(client: AsyncClient, strong_password: str) -> None:
    h, me = await _user(client, "Mine LLP", "mine@firm.co", strong_password)
    other_h, _ = await _user(client, "Other LLP", "other@firm.co", strong_password)
    mine = (await client.post(f"{API}/matters", headers=h, json={"title": "Mine", "client_name": "X", "assigned_to": me["id"]})).json()
    await client.post(f"{API}/matters", headers=h, json={"title": "Not mine", "client_name": "Y"})
    await client.post(f"{API}/matters", headers=other_h, json={"title": "Other firm", "client_name": "Z"})

    everyone = (await client.get(f"{API}/matters/board", headers=h)).json()
    assert everyone["total"] == 2
    just_me = (await client.get(f"{API}/matters/board", headers=h, params={"user_id": me["id"]})).json()
    assert [c["id"] for col in just_me["columns"] for c in col["matters"]] == [mine["id"]]
    assert (await client.get(f"{API}/matters/board", headers=other_h)).json()["total"] == 1
