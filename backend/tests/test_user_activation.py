"""Admin user activation — deactivate blocks sign-in + revokes sessions; reactivate; guards."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _owner(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
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


async def test_deactivate_and_reactivate(client: AsyncClient, strong_password: str) -> None:
    owner_h, _ = await _owner(client, "Active LLP", "owner@active.co", strong_password)

    created = await client.post(
        f"{API}/tenants/users", headers=owner_h,
        json={"email": "member@active.co", "full_name": "Team Member", "role_codes": ["associate"]},
    )
    assert created.status_code == 201
    member_id = created.json()["user"]["id"]
    temp = created.json()["temporary_password"]

    # The member can sign in and gets a session.
    login = await client.post(f"{API}/auth/login", json={"email": "member@active.co", "password": temp})
    assert login.status_code == 200
    member_refresh = login.json()["refresh_token"]

    # Deactivate: sign-in is blocked and the existing session is revoked.
    deact = await client.post(f"{API}/tenants/users/{member_id}/deactivate", headers=owner_h)
    assert deact.status_code == 200 and deact.json()["is_active"] is False
    assert (await client.post(f"{API}/auth/login", json={"email": "member@active.co", "password": temp})).status_code == 403
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": member_refresh})).status_code == 401

    # Reactivate: sign-in works again.
    react = await client.post(f"{API}/tenants/users/{member_id}/activate", headers=owner_h)
    assert react.status_code == 200 and react.json()["is_active"] is True
    assert (await client.post(f"{API}/auth/login", json={"email": "member@active.co", "password": temp})).status_code == 200

    actions = {e["action"] for e in (await client.get(f"{API}/admin/audit", headers=owner_h)).json()}
    assert {"user.deactivated", "user.activated"} <= actions


async def test_cannot_deactivate_self(client: AsyncClient, strong_password: str) -> None:
    owner_h, owner = await _owner(client, "Solo LLP", "solo@solo.co", strong_password)
    resp = await client.post(f"{API}/tenants/users/{owner['id']}/deactivate", headers=owner_h)
    assert resp.status_code == 422
    # Still active.
    assert (await client.get(f"{API}/auth/me", headers=owner_h)).status_code == 200
