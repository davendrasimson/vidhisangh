"""Morning matter-board digest: who gets it, what it says, sent once a day."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.push import PushMessage
from app.modules.matters import board_digest
from app.modules.notifications.models import BoardDigestSend
from tests.test_matters import API, _user

pytestmark = pytest.mark.asyncio


class PushRecorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, PushMessage]] = []

    async def send(self, device_token, message):  # noqa: ANN001
        self.sent.append((device_token, message))
        return "sent"


async def test_digest_lists_only_matters_needing_attention_and_sends_once(
    client: AsyncClient, strong_password: str, session_factory,
) -> None:
    today = date.today()
    h, me = await _user(client, "Digest LLP", "digest@firm.co", strong_password)
    await client.post(f"{API}/notifications/devices", headers=h, json={"token": "fcm-" + "d" * 40, "platform": "android"})
    # Needs attention: limitation passed and an overdue task.
    a = (await client.post(f"{API}/matters", headers=h, json={"title": "Urgent appeal", "client_name": "A", "lead_counsel_id": me["id"],
                                                              "limitation_date": (today - timedelta(days=2)).isoformat()})).json()
    await client.post(f"{API}/matters/{a['id']}/tasks", headers=h, json={"title": "File appeal", "due_on": (today - timedelta(days=1)).isoformat()})
    # Fine: a hearing next week and an open task — no attention flag.
    b = (await client.post(f"{API}/matters", headers=h, json={"title": "Calm matter", "client_name": "B", "assigned_to": me["id"]})).json()
    await client.post(f"{API}/matters/{b['id']}/hearings", headers=h, json={"scheduled_on": f"{(today + timedelta(days=6)).isoformat()}T05:00:00Z"})
    await client.post(f"{API}/matters/{b['id']}/tasks", headers=h, json={"title": "Prepare", "due_on": (today + timedelta(days=3)).isoformat()})
    # Someone else's firm: never in this member's digest.
    h2, _ = await _user(client, "Other LLP", "other2@firm.co", strong_password)
    await client.post(f"{API}/matters", headers=h2, json={"title": "Other firm stale", "client_name": "Z",
                                                          "limitation_date": (today - timedelta(days=9)).isoformat()})

    async with session_factory() as session:
        due = await board_digest.collect(session, today)
        assert len(due) == 1 and due[0].user_id.__str__() == me["id"] and due[0].push and due[0].phone is None
        assert due[0].items == [f"1. Urgent appeal ({a['matter_number']}): limitation passed, overdue task"]

        push = PushRecorder()
        assert await board_digest.send_digests(session, None, today, due, push=push) == {"sent": 1, "already": 0, "failed": 0}
        row = (await session.execute(select(BoardDigestSend))).scalar_one()
        assert row.status == "sent" and row.detail == "push" and row.matter_count == 1
        (token, message), = push.sent
        assert token.startswith("fcm-") and message.title == "Your matter board" and message.link == "/app/matters/board"
        assert message.body == f"1 matter needs attention: Urgent appeal ({a['matter_number']}): limitation passed, overdue task"

        # A rerun the same day sends nothing more.
        assert await board_digest.send_digests(session, None, today, due, push=PushRecorder()) == {"sent": 0, "already": 1, "failed": 0}

    # Push switched off: no digest for this member.
    await client.put(f"{API}/notifications/preferences/push", headers=h, json={"enabled": False, "types": []})
    async with session_factory() as session:
        assert await board_digest.collect(session, today) == []


async def test_item_list_is_capped_for_the_template() -> None:
    items = [f"{i}. Matter number {i} (M-{i:04d}): no next step" for i in range(1, 60)]
    text = board_digest.item_list(items)
    assert len(text) <= board_digest.LIST_LIMIT + 60 and "more on the board" in text
    assert board_digest.item_list(items[:2]) == "; ".join(items[:2])
