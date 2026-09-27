"""Messaging module tests (cross-tenant global chat layer)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _register(client: AsyncClient, org: str, email: str, pw: str) -> dict:
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
    return resp.json()


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
    tokens = await _register(client, org, email, pw)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    return headers, me


async def test_direct_conversation_is_deduplicated(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "m1@firma.co", strong_password)
    _h2, me2 = await _user(client, "Firm B", "m2@firmb.co", strong_password)

    first = await client.post(f"{API}/conversations/direct/{me2['id']}", headers=h1)
    assert first.status_code == 201, first.text
    assert first.json()["type"] == "direct"
    assert len(first.json()["participants"]) == 2

    # Opening the same 1:1 again returns the existing conversation.
    again = await client.post(f"{API}/conversations/direct/{me2['id']}", headers=h1)
    assert again.status_code == 201
    assert again.json()["id"] == first.json()["id"]


async def test_send_message_and_unread(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "s1@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "s2@firmb.co", strong_password)
    conv_id = (await client.post(f"{API}/conversations/direct/{me2['id']}", headers=h1)).json()["id"]

    sent = await client.post(
        f"{API}/conversations/{conv_id}/messages", headers=h1, json={"body": "Hello counsel!"}
    )
    assert sent.status_code == 201, sent.text

    # Recipient sees an unread conversation with the preview.
    convos = (await client.get(f"{API}/conversations", headers=h2)).json()
    row = next(c for c in convos if c["id"] == conv_id)
    assert row["unread_count"] == 1
    assert row["last_message_preview"] == "Hello counsel!"

    # Opening the thread returns the message and marks it read.
    msgs = await client.get(f"{API}/conversations/{conv_id}/messages", headers=h2)
    assert [m["body"] for m in msgs.json()] == ["Hello counsel!"]
    convos = (await client.get(f"{API}/conversations", headers=h2)).json()
    assert next(c for c in convos if c["id"] == conv_id)["unread_count"] == 0

    # The sender never has unread of their own message.
    convos1 = (await client.get(f"{API}/conversations", headers=h1)).json()
    assert next(c for c in convos1 if c["id"] == conv_id)["unread_count"] == 0


async def test_group_conversation(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "g1@firma.co", strong_password)
    _h2, me2 = await _user(client, "Firm B", "g2@firmb.co", strong_password)
    h3, me3 = await _user(client, "Firm C", "g3@firmc.co", strong_password)

    created = await client.post(
        f"{API}/conversations/group",
        headers=h1,
        json={"title": "Arbitration panel", "participant_ids": [me2["id"], me3["id"]]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["type"] == "group"
    assert created.json()["title"] == "Arbitration panel"
    assert len(created.json()["participants"]) == 3
    conv_id = created.json()["id"]

    await client.post(f"{API}/conversations/{conv_id}/messages", headers=h1, json={"body": "Kickoff"})
    convos3 = (await client.get(f"{API}/conversations", headers=h3)).json()
    assert next(c for c in convos3 if c["id"] == conv_id)["unread_count"] == 1


async def test_cannot_message_self(client: AsyncClient, strong_password: str) -> None:
    h1, me1 = await _user(client, "Firm A", "self@firma.co", strong_password)
    resp = await client.post(f"{API}/conversations/direct/{me1['id']}", headers=h1)
    assert resp.status_code == 422


async def test_non_participant_forbidden(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "n1@firma.co", strong_password)
    _h2, me2 = await _user(client, "Firm B", "n2@firmb.co", strong_password)
    h3, _ = await _user(client, "Firm C", "n3@firmc.co", strong_password)
    conv_id = (await client.post(f"{API}/conversations/direct/{me2['id']}", headers=h1)).json()["id"]

    assert (await client.get(f"{API}/conversations/{conv_id}", headers=h3)).status_code == 403
    assert (await client.get(f"{API}/conversations/{conv_id}/messages", headers=h3)).status_code == 403
    resp = await client.post(
        f"{API}/conversations/{conv_id}/messages", headers=h3, json={"body": "intruder"}
    )
    assert resp.status_code == 403


async def test_leave_group_but_not_direct(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "l1@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "l2@firmb.co", strong_password)

    direct_id = (await client.post(f"{API}/conversations/direct/{me2['id']}", headers=h1)).json()["id"]
    assert (await client.post(f"{API}/conversations/{direct_id}/leave", headers=h1)).status_code == 422

    group_id = (
        await client.post(
            f"{API}/conversations/group",
            headers=h1,
            json={"title": "Case team", "participant_ids": [me2["id"]]},
        )
    ).json()["id"]
    assert (await client.post(f"{API}/conversations/{group_id}/leave", headers=h2)).status_code == 204
    # h2 no longer sees the group.
    convos2 = (await client.get(f"{API}/conversations", headers=h2)).json()
    assert all(c["id"] != group_id for c in convos2)
