"""In-app notifications tests — events across modules create notifications."""

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


async def test_mention_creates_notification(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "na1@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "na2@firmb.co", strong_password)

    await client.post(
        f"{API}/network/posts",
        headers=h1,
        json={"content": "Great work!", "mention_ids": [me2["id"]]},
    )

    notifs = await client.get(f"{API}/notifications", headers=h2)
    assert notifs.status_code == 200
    assert len(notifs.json()) == 1
    n = notifs.json()[0]
    assert n["type"] == "mention"
    assert n["is_read"] is False
    assert "mentioned you" in n["message"]

    count = await client.get(f"{API}/notifications/unread-count", headers=h2)
    assert count.json()["count"] == 1

    assert (await client.post(f"{API}/notifications/{n['id']}/read", headers=h2)).status_code == 204
    assert (await client.get(f"{API}/notifications/unread-count", headers=h2)).json()["count"] == 0


async def test_connection_and_invite_notifications(client: AsyncClient, strong_password: str) -> None:
    h1, me1 = await _user(client, "Firm A", "nc1@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "nc2@firmb.co", strong_password)

    # Connection request notifies the addressee.
    await client.post(f"{API}/network/connections/{me2['id']}", headers=h1, json={})
    n2 = (await client.get(f"{API}/notifications", headers=h2)).json()
    assert any(x["type"] == "connection_request" for x in n2)

    # Group invite notifies the invitee.
    group = (
        await client.post(f"{API}/groups", headers=h1, json={"name": "Panel"})
    ).json()
    await client.post(f"{API}/groups/{group['id']}/invite/{me2['id']}", headers=h1)
    n2 = (await client.get(f"{API}/notifications", headers=h2)).json()
    assert any(x["type"] == "group_invite" for x in n2)

    # The actor never notifies themselves.
    assert (await client.get(f"{API}/notifications", headers=h1)).json() == []

    # Mark-all-read clears the badge.
    assert (await client.post(f"{API}/notifications/read-all", headers=h2)).status_code == 204
    assert (await client.get(f"{API}/notifications/unread-count", headers=h2)).json()["count"] == 0


async def test_cannot_read_others_notification(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "no1@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "no2@firmb.co", strong_password)
    h3, _ = await _user(client, "Firm C", "no3@firmc.co", strong_password)

    await client.post(
        f"{API}/network/posts", headers=h1, json={"content": "hi", "mention_ids": [me2["id"]]}
    )
    notif_id = (await client.get(f"{API}/notifications", headers=h2)).json()[0]["id"]

    # A third party cannot mark someone else's notification read.
    assert (await client.post(f"{API}/notifications/{notif_id}/read", headers=h3)).status_code == 403
