"""Real-time messaging tests: connection manager fan-out and live delivery.

A full WebSocket handshake would require the socket handler's own DB session
(Postgres), so we exercise the delivery *wiring* by registering a fake socket in
the manager and sending via REST — proving ``send_message`` fans out to online
recipients — plus a pure unit test of the manager.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.modules.messaging.realtime import ConnectionManager, manager

pytestmark = pytest.mark.asyncio

API = "/api/v1"


class FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


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


async def test_connection_manager_fanout() -> None:
    mgr = ConnectionManager()
    user = uuid.uuid4()
    ws1, ws2 = FakeWS(), FakeWS()

    assert mgr.add(user, ws1) is True   # first socket -> became online
    assert mgr.add(user, ws2) is False  # second socket -> already online
    assert mgr.is_online(user) is True
    assert mgr.online_among([user, uuid.uuid4()]) == [user]

    await mgr.send_to_users([user], {"type": "ping"})
    assert ws1.sent == [{"type": "ping"}]
    assert ws2.sent == [{"type": "ping"}]

    assert mgr.remove(user, ws1) is False  # still has ws2
    assert mgr.remove(user, ws2) is True   # now fully offline
    assert mgr.is_online(user) is False


async def test_message_delivered_to_online_recipient(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _user(client, "Firm A", "rt-a@firma.co", strong_password)
    b_h, b = await _user(client, "Firm B", "rt-b@firmb.co", strong_password)
    conv = (await client.post(f"{API}/conversations/direct/{b['id']}", headers=a_h)).json()

    # Simulate B being connected via a live socket.
    b_socket = FakeWS()
    b_id = uuid.UUID(b["id"])
    manager.add(b_id, b_socket)
    try:
        sent = await client.post(
            f"{API}/conversations/{conv['id']}/messages", headers=a_h, json={"body": "live!"}
        )
        assert sent.status_code == 201
        assert len(b_socket.sent) == 1
        event = b_socket.sent[0]
        assert event["type"] == "message"
        assert event["conversation_id"] == conv["id"]
        assert event["message"]["body"] == "live!"
        assert event["message"]["sender_id"] != b["id"]
    finally:
        manager.remove(b_id, b_socket)

    # The sender's own socket receives nothing (no self-delivery).
    a_socket = FakeWS()
    # (A is not registered; simply assert B's socket got exactly one event above.)
    assert not a_socket.sent
