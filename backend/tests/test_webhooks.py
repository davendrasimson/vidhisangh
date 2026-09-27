"""Webhooks — registration, signed test delivery, event fan-out, isolation."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.core.webhook_transport import RecordingTransport
from app.modules.webhooks.service import dispatcher, verify_signature

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> dict:
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
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_register_test_and_fanout(
    client: AsyncClient, strong_password: str, webhook_transport: RecordingTransport
) -> None:
    h = await _user(client, "Hook LLP", "hook@firm.co", strong_password)

    events = (await client.get(f"{API}/webhooks/events", headers=h)).json()
    assert {"ping", "matter.created"} <= {e["key"] for e in events}

    # Unknown event types are rejected.
    assert (await client.post(f"{API}/webhooks", headers=h,
                              json={"url": "https://x.test/h", "event_types": ["nope"]})).status_code == 422

    created = await client.post(
        f"{API}/webhooks", headers=h,
        json={"url": "https://x.test/hook", "description": "CI",
              "event_types": ["matter.created", "ping"]},
    )
    assert created.status_code == 201, created.text
    secret = created.json()["secret"]
    assert secret.startswith("whsec_")
    wid = created.json()["id"]

    # Send a test ping — recorded as a successful delivery, signed with the secret.
    test = await client.post(f"{API}/webhooks/{wid}/test", headers=h)
    assert test.status_code == 200
    assert test.json()["event_type"] == "ping" and test.json()["status"] == "success"
    assert test.json()["status_code"] == 200

    # The transport received a timestamped ``t=…,v1=…`` signature over
    # ``"{t}.{body}"``. The replayable body-only legacy header is retired.
    call = webhook_transport.calls[-1]
    assert verify_signature(secret, call["headers"]["X-VidhiSangh-Signature"], call["body"])
    assert "X-VidhiSangh-Signature-Legacy" not in call["headers"]
    assert json.loads(call["body"])["event"] == "ping"

    # Creating a matter queues a matter.created delivery for the subscribed hook;
    # it is delivered off the request path (drain = the background worker).
    await client.post(f"{API}/matters", headers=h, json={"title": "New Matter", "client_name": "C"})
    assert dispatcher.pending == 1
    await dispatcher.drain()
    deliveries = (await client.get(f"{API}/webhooks/{wid}/deliveries", headers=h)).json()
    kinds = [d["event_type"] for d in deliveries]
    assert "matter.created" in kinds and "ping" in kinds
    assert all(d["detail"] == "delivered" or d["detail"].startswith("delivered (attempt") for d in deliveries)

    # Deactivating stops fan-out.
    await client.patch(f"{API}/webhooks/{wid}", headers=h, json={"is_active": False})
    await client.post(f"{API}/matters", headers=h, json={"title": "Another Matter", "client_name": "C"})
    await dispatcher.drain()
    after = (await client.get(f"{API}/webhooks/{wid}/deliveries", headers=h)).json()
    assert [d["event_type"] for d in after].count("matter.created") == 1


async def test_webhook_isolation_and_delete(client: AsyncClient, strong_password: str) -> None:
    a = await _user(client, "Firm A", "wa@firma.co", strong_password)
    b = await _user(client, "Firm B", "wb@firmb.co", strong_password)

    wid = (
        await client.post(f"{API}/webhooks", headers=a,
                          json={"url": "https://a.test/h", "event_types": ["ping"]})
    ).json()["id"]

    # Firm B cannot see or delete Firm A's webhook.
    assert (await client.get(f"{API}/webhooks", headers=b)).json() == []
    assert (await client.request("DELETE", f"{API}/webhooks/{wid}", headers=b)).status_code == 404

    assert (await client.request("DELETE", f"{API}/webhooks/{wid}", headers=a)).status_code == 204
    assert (await client.get(f"{API}/webhooks", headers=a)).json() == []
