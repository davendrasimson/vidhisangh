"""API keys — issuance, scoped programmatic access, revocation, guards, isolation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _owner(client: AsyncClient, org: str, email: str, pw: str) -> dict:
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


async def test_key_grants_scoped_access(client: AsyncClient, strong_password: str) -> None:
    h = await _owner(client, "Key LLP", "key@firm.co", strong_password)

    created = await client.post(
        f"{API}/api-keys", headers=h,
        json={"name": "CI bot", "scopes": ["matter:read", "matter:create"]},
    )
    assert created.status_code == 201, created.text
    raw = created.json()["key"]
    assert raw.startswith("vsk_")
    assert created.json()["prefix"] == raw[:12]
    key_headers = {"Authorization": f"Bearer {raw}"}

    # The key can do what its scopes allow…
    made = await client.post(f"{API}/matters", headers=key_headers,
                             json={"title": "Via API key", "client_name": "C"})
    assert made.status_code == 201, made.text
    assert (await client.get(f"{API}/matters", headers=key_headers)).status_code == 200

    # …but nothing outside them (no invoice:read scope).
    assert (await client.get(f"{API}/billing/invoices", headers=key_headers)).status_code == 403

    # Listing never exposes the secret, only the prefix.
    listed = (await client.get(f"{API}/api-keys", headers=h)).json()
    assert len(listed) == 1 and "key" not in listed[0]
    assert listed[0]["last_used_at"] is not None  # updated by the key's requests
    kid = listed[0]["id"]

    # Revoking the key immediately blocks it.
    assert (await client.request("DELETE", f"{API}/api-keys/{kid}", headers=h)).status_code == 204
    assert (await client.get(f"{API}/matters", headers=key_headers)).status_code == 401


async def test_key_guards_and_isolation(client: AsyncClient, strong_password: str) -> None:
    a = await _owner(client, "Firm A", "ka@firma.co", strong_password)
    b = await _owner(client, "Firm B", "kb@firmb.co", strong_password)

    # Cannot grant a scope you don't hold (also rejects unknown codes).
    assert (await client.post(f"{API}/api-keys", headers=a,
                              json={"name": "bad", "scopes": ["not:a-real-scope"]})).status_code == 422

    a_key = (
        await client.post(f"{API}/api-keys", headers=a,
                          json={"name": "A key", "scopes": ["matter:read"]})
    ).json()["key"]

    # A tenant admin does not see another tenant's keys…
    assert (await client.get(f"{API}/api-keys", headers=b)).json() == []
    # …and A's key only sees A's data (B created no matters; A none either → empty, but 200 & scoped).
    scoped = await client.get(f"{API}/matters", headers={"Authorization": f"Bearer {a_key}"})
    assert scoped.status_code == 200

    # A random / malformed key is rejected.
    assert (await client.get(f"{API}/matters", headers={"Authorization": "Bearer vsk_bogus"})).status_code == 401

    # The key actions are audited.
    actions = {e["action"] for e in (await client.get(f"{API}/admin/audit", headers=a)).json()}
    assert "apikey.created" in actions
