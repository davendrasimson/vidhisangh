"""Admin system dashboard — app info, checks, integration & channel config status."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

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


async def test_system_overview(client: AsyncClient, strong_password: str) -> None:
    h = await _user(client, "Ops LLP", "ops@firm.co", strong_password)

    resp = await client.get(f"{API}/admin/system", headers=h)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["app"]["name"] and data["app"]["version"]
    # The injected (SQLite) session answers SELECT 1.
    checks = {c["name"]: c["status"] for c in data["checks"]}
    assert checks["database"] == "ok"
    assert "redis" in checks

    # Integrations report status without leaking secrets.
    integ = {i["key"]: i["status"] for i in data["integrations"]}
    assert integ["email"] == "log-fallback"       # no SMTP host in tests
    assert integ["razorpay"] == "mock"            # no keys in tests
    assert "storage" in integ

    # Channel provider status covers every channel.
    channels = {c["channel"]: c["status"] for c in data["channels"]}
    assert channels["in_app"] == "live"
    assert channels["email"] == "log-fallback"
    assert channels["sms"] == "not_configured"
