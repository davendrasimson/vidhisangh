"""Feature flags — catalog defaults, tenant overrides, resolve, isolation."""

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


async def test_catalog_defaults_and_override(client: AsyncClient, strong_password: str) -> None:
    h = await _user(client, "Flag LLP", "flag@firm.co", strong_password)

    flags = (await client.get(f"{API}/admin/feature-flags", headers=h)).json()
    by_key = {f["key"]: f for f in flags}
    assert by_key["marketplace"]["enabled"] is True and by_key["marketplace"]["overridden"] is False
    assert by_key["online_payments"]["enabled"] is True  # default on since flags are enforced (A-32); tenants may turn it off

    resolved = (await client.get(f"{API}/feature-flags", headers=h)).json()
    assert resolved["marketplace"] is True and resolved["online_payments"] is True

    # Override: turn payments off, marketplace off.
    off = await client.put(f"{API}/admin/feature-flags/online_payments", headers=h, json={"enabled": False})
    assert off.status_code == 200 and off.json()["enabled"] is False and off.json()["overridden"] is True
    assert (await client.put(f"{API}/admin/feature-flags/marketplace", headers=h,
                             json={"enabled": False})).json()["enabled"] is False

    resolved = (await client.get(f"{API}/feature-flags", headers=h)).json()
    assert resolved["online_payments"] is False and resolved["marketplace"] is False
    # Enforcement (A-32): a disabled flag closes the API, not just the UI.
    assert (await client.get(f"{API}/marketplace/listings", headers=h)).status_code in (403, 404)

    # Unknown flags are rejected.
    assert (await client.put(f"{API}/admin/feature-flags/does_not_exist", headers=h,
                             json={"enabled": True})).status_code == 404


async def test_flag_tenant_isolation(client: AsyncClient, strong_password: str) -> None:
    a = await _user(client, "Firm A", "fa@firma.co", strong_password)
    b = await _user(client, "Firm B", "fb@firmb.co", strong_password)

    await client.put(f"{API}/admin/feature-flags/marketplace", headers=a, json={"enabled": False})

    # Firm B is unaffected by Firm A's override.
    assert (await client.get(f"{API}/feature-flags", headers=b)).json()["marketplace"] is True
    assert (await client.get(f"{API}/feature-flags", headers=a)).json()["marketplace"] is False
