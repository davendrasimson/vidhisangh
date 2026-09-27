"""Admin console — audit trail of admin actions, user listing, isolation."""

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


async def test_audit_records_admin_actions(client: AsyncClient, strong_password: str) -> None:
    email = "admin@firm.co"
    h = await _user(client, "Audit LLP", email, strong_password)

    await client.put(f"{API}/admin/feature-flags/marketplace", headers=h, json={"enabled": False})
    await client.put(f"{API}/admin/subscription", headers=h, json={"tier": "solo"})

    events = (await client.get(f"{API}/admin/audit", headers=h)).json()
    actions = {e["action"] for e in events}
    assert actions == {"feature_flag.updated", "subscription.changed"}
    assert all(e["actor_label"] == email for e in events)
    flag_event = next(e for e in events if e["action"] == "feature_flag.updated")
    assert flag_event["entity_id"] == "marketplace" and "disabled" in flag_event["summary"]

    # Action filter narrows the log.
    filtered = (await client.get(f"{API}/admin/audit?action=subscription.changed", headers=h)).json()
    assert len(filtered) == 1 and filtered[0]["entity_id"] == "solo"


async def test_user_listing_and_audit_isolation(client: AsyncClient, strong_password: str) -> None:
    a = await _user(client, "Firm A", "owner@firma.co", strong_password)
    b = await _user(client, "Firm B", "owner@firmb.co", strong_password)

    await client.put(f"{API}/admin/feature-flags/analytics", headers=a, json={"enabled": False})

    users = (await client.get(f"{API}/tenants/users", headers=a)).json()
    assert len(users) == 1
    assert users[0]["email"] == "owner@firma.co"
    assert any(r["code"] == "org_admin" for r in users[0]["roles"])

    # Firm B does not see Firm A's audit trail or users.
    assert (await client.get(f"{API}/admin/audit", headers=b)).json() == []
    b_users = (await client.get(f"{API}/tenants/users", headers=b)).json()
    assert [u["email"] for u in b_users] == ["owner@firmb.co"]
