"""Notification channels — default preferences, rule-engine routing, delivery log."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


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


async def _connect(client: AsyncClient, sender: dict, recipient_id: str) -> None:
    r = await client.post(
        f"{API}/network/connections/{recipient_id}", headers=sender, json={"message": "hi"}
    )
    assert r.status_code == 201, r.text


async def test_default_preferences_and_in_app_delivery(
    client: AsyncClient, strong_password: str
) -> None:
    a_h, _ = await _user(client, "Firm A", "na@firma.co", strong_password)
    b_h, b = await _user(client, "Firm B", "nb@firmb.co", strong_password)

    prefs = (await client.get(f"{API}/notifications/preferences", headers=b_h)).json()
    enabled = {p["channel"]: p["enabled"] for p in prefs}
    assert enabled["in_app"] is True
    assert enabled["email"] is False and enabled["sms"] is False

    await _connect(client, a_h, b["id"])

    notes = (await client.get(f"{API}/notifications", headers=b_h)).json()
    assert len(notes) == 1 and notes[0]["type"] == "connection_request"

    deliveries = (await client.get(f"{API}/notifications/deliveries", headers=b_h)).json()
    assert [(d["channel"], d["status"]) for d in deliveries] == [("in_app", "sent")]


async def test_rule_engine_routes_to_enabled_channels(
    client: AsyncClient, strong_password: str
) -> None:
    c_h, _ = await _user(client, "Firm C", "nc@firmc.co", strong_password)
    b_h, b = await _user(client, "Firm B", "nb2@firmb.co", strong_password)

    # Enable email (falls back to the log provider → "sent") and sms (no provider → "skipped").
    assert (await client.put(f"{API}/notifications/preferences/email", headers=b_h,
                             json={"enabled": True, "types": []})).status_code == 200
    assert (await client.put(f"{API}/notifications/preferences/sms", headers=b_h,
                             json={"enabled": True, "types": []})).status_code == 200
    # In-app cannot be turned off.
    assert (await client.put(f"{API}/notifications/preferences/in_app", headers=b_h,
                             json={"enabled": False, "types": []})).status_code == 403

    await _connect(client, c_h, b["id"])

    deliveries = (await client.get(f"{API}/notifications/deliveries", headers=b_h)).json()
    by_channel = {d["channel"]: d for d in deliveries}
    assert by_channel["in_app"]["status"] == "sent"
    assert by_channel["email"]["status"] == "sent" and by_channel["email"]["detail"] == "via log"
    assert by_channel["sms"]["status"] == "skipped"


async def test_type_scoped_rule_filters_channel(
    client: AsyncClient, strong_password: str
) -> None:
    c_h, _ = await _user(client, "Firm C", "nc2@firmc.co", strong_password)
    b_h, b = await _user(client, "Firm B", "nb3@firmb.co", strong_password)

    # Email only for group invites — a connection request must NOT route to email.
    await client.put(f"{API}/notifications/preferences/email", headers=b_h,
                     json={"enabled": True, "types": ["group_invite"]})

    await _connect(client, c_h, b["id"])

    deliveries = (await client.get(f"{API}/notifications/deliveries", headers=b_h)).json()
    channels = {d["channel"] for d in deliveries}
    assert "in_app" in channels
    assert "email" not in channels
