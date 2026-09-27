"""Subscription plans — catalog, current subscription, usage, plan change."""

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


async def test_catalog_subscription_and_change(client: AsyncClient, strong_password: str) -> None:
    h = await _user(client, "Plan LLP", "plan@firm.co", strong_password)

    plans = (await client.get(f"{API}/admin/plans", headers=h)).json()
    by_tier = {p["tier"]: p for p in plans}
    assert set(by_tier) == {"free", "solo", "team", "firm", "enterprise"}
    assert by_tier["free"]["price_inr"] == 0 and by_tier["free"]["is_current"] is True
    assert by_tier["enterprise"]["price_inr"] is None  # custom
    assert by_tier["firm"]["max_matters"] is None      # unlimited

    # A fresh tenant starts on Free / trial with one user and no matters.
    sub = (await client.get(f"{API}/admin/subscription", headers=h)).json()
    assert sub["plan"]["tier"] == "free" and sub["status"] == "trial"
    assert sub["usage"]["users"] == 1 and sub["usage"]["matters"] == 0

    # Usage tracks live data.
    await client.post(f"{API}/matters", headers=h, json={"title": "Matter One", "client_name": "C"})
    sub = (await client.get(f"{API}/admin/subscription", headers=h)).json()
    assert sub["usage"]["matters"] == 1

    # Upgrading activates the workspace.
    changed = await client.put(f"{API}/admin/subscription", headers=h, json={"tier": "team"})
    assert changed.status_code == 200
    assert changed.json()["plan"]["tier"] == "team" and changed.json()["status"] == "active"
    assert changed.json()["plan"]["is_current"] is True

    plans = (await client.get(f"{API}/admin/plans", headers=h)).json()
    assert {p["tier"]: p["is_current"] for p in plans}["team"] is True
