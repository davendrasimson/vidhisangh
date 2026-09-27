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


# ─── Per-tenant Slack, address masking, retention (audit P-11 / P-12) ──
import uuid  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

from sqlalchemy import update  # noqa: E402

from app.modules.notifications.models import NotificationDelivery  # noqa: E402
from app.modules.notifications.service import (  # noqa: E402
    count_deliveries,
    mask_emails,
    purge_old_deliveries,
    set_slack_sender,
)
from app.scripts import retention_purge  # noqa: E402


async def test_tenant_slack_webhook_is_used_for_tenant_notifications(
    client: AsyncClient, strong_password: str
) -> None:
    a_h, _ = await _user(client, "Firm A", "sa@firma.co", strong_password)
    b_h, b = await _user(client, "Firm B", "sb@firmb.co", strong_password)
    await client.put(f"{API}/notifications/preferences/slack", headers=b_h, json={"enabled": True, "types": []})

    # Without a tenant webhook the route is skipped (the operator-wide hook is never used).
    await _connect(client, a_h, b["id"])
    deliveries = (await client.get(f"{API}/notifications/deliveries", headers=b_h)).json()
    slack = [d for d in deliveries if d["channel"] == "slack"]
    assert slack and slack[0]["status"] == "skipped" and "no Slack webhook configured" in slack[0]["detail"]

    # Configure the firm's own hook (validated as a public https URL; only the host is echoed).
    assert (await client.patch(f"{API}/tenants/current/notifications", headers=b_h,
                               json={"slack_webhook": "http://hooks.slack.com/services/T/B/x"})).status_code == 422
    assert (await client.patch(f"{API}/tenants/current/notifications", headers=b_h,
                               json={"slack_webhook": "https://private.test/services/T/B/x"})).status_code == 422
    ok = await client.patch(f"{API}/tenants/current/notifications", headers=b_h,
                            json={"slack_webhook": "https://hooks.slack.com/services/T/B/secret"})
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"slack_webhook_configured": True, "slack_webhook_host": "hooks.slack.com"}
    assert "secret" not in (await client.get(f"{API}/tenants/current/notifications", headers=b_h)).text
    # A generic settings write cannot smuggle a URL in or wipe the block.
    await client.patch(f"{API}/tenants/current", headers=b_h,
                       json={"settings": {"branding": {"x": 1}, "notifications": {"slack_webhook": "https://evil.test/"}}})
    assert (await client.get(f"{API}/tenants/current/notifications", headers=b_h)).json()["slack_webhook_host"] == "hooks.slack.com"

    sent: list[tuple[str, str]] = []

    async def capture(url: str, text: str) -> None:
        sent.append((url, text))

    set_slack_sender(capture)
    try:
        c_h, _ = await _user(client, "Firm C", "sc@firmc.co", strong_password)
        await _connect(client, c_h, b["id"])
    finally:
        set_slack_sender(None)
    assert sent and sent[0][0] == "https://hooks.slack.com/services/T/B/secret"
    assert "connection request" in sent[0][1]
    deliveries = (await client.get(f"{API}/notifications/deliveries", headers=b_h)).json()
    assert "via tenant slack" in {d["detail"] for d in deliveries if d["channel"] == "slack"}

    # Removing it.
    off = await client.patch(f"{API}/tenants/current/notifications", headers=b_h, json={"slack_webhook": None})
    assert off.json()["slack_webhook_configured"] is False


async def test_delivery_details_never_contain_email_addresses() -> None:
    assert mask_emails("SMTP 550 recipient adv.rao@firm.co.in rejected") == "SMTP 550 recipient ***@firm.co.in rejected"
    assert mask_emails(None) is None and mask_emails("via log") == "via log"


async def test_purge_old_deliveries(client: AsyncClient, strong_password: str, session_factory) -> None:
    a_h, _ = await _user(client, "Firm A", "pa@firma.co", strong_password)
    b_h, b = await _user(client, "Firm B", "pb@firmb.co", strong_password)
    await _connect(client, a_h, b["id"])  # one in_app delivery row for b
    async with session_factory() as s:
        assert await count_deliveries(s) == 1
        old = datetime.now(UTC) - timedelta(days=91)
        await s.execute(update(NotificationDelivery).values(created_at=old))
        await s.commit()
    async with session_factory() as s:
        assert await purge_old_deliveries(s, days=90) == 1
        await s.commit()
        assert await count_deliveries(s) == 0
    # The management command runs it through the registry.
    assert retention_purge.purge_notification_deliveries in retention_purge.PURGES
