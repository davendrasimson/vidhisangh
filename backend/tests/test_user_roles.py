"""Admin user management — invite (create), role listing, role assignment, guards."""

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


async def test_invite_and_role_assignment(client: AsyncClient, strong_password: str) -> None:
    owner_h, owner = await _owner(client, "Roles LLP", "owner@roles.co", strong_password)

    # Assignable roles include system roles but never the platform superuser.
    roles = (await client.get(f"{API}/tenants/roles", headers=owner_h)).json()
    codes = {r["code"] for r in roles}
    assert "org_admin" in codes and "associate" in codes
    assert "system_admin" not in codes

    # Invite a colleague as an associate.
    created = await client.post(
        f"{API}/tenants/users", headers=owner_h,
        json={"email": "junior@roles.co", "full_name": "Junior Advocate", "role_codes": ["associate"]},
    )
    assert created.status_code == 201, created.text
    temp = created.json()["temporary_password"]
    new_id = created.json()["user"]["id"]
    assert [r["code"] for r in created.json()["user"]["roles"]] == ["associate"]

    # The new user can sign in with the temporary password.
    login = await client.post(f"{API}/auth/login", json={"email": "junior@roles.co", "password": temp})
    assert login.status_code == 200, login.text
    junior_h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    # …but as an associate cannot manage roles.
    assert (await client.put(f"{API}/tenants/users/{owner['id']}/roles", headers=junior_h,
                             json={"role_codes": ["org_admin"]})).status_code == 403

    # Owner promotes the colleague to partner.
    promoted = await client.put(f"{API}/tenants/users/{new_id}/roles", headers=owner_h,
                                json={"role_codes": ["partner", "associate"]})
    assert promoted.status_code == 200
    assert {r["code"] for r in promoted.json()["roles"]} == {"partner", "associate"}


async def test_role_assignment_guards(client: AsyncClient, strong_password: str) -> None:
    owner_h, owner = await _owner(client, "Guard LLP", "owner@guard.co", strong_password)

    # Cannot edit your own roles (self-lockout guard).
    assert (await client.put(f"{API}/tenants/users/{owner['id']}/roles", headers=owner_h,
                             json={"role_codes": ["associate"]})).status_code == 422

    new_id = (
        await client.post(f"{API}/tenants/users", headers=owner_h,
                          json={"email": "x@guard.co", "full_name": "New Person", "role_codes": ["clerk"]})
    ).json()["user"]["id"]

    # Cannot grant the platform superuser role, or an unknown role.
    assert (await client.put(f"{API}/tenants/users/{new_id}/roles", headers=owner_h,
                             json={"role_codes": ["system_admin"]})).status_code == 422
    assert (await client.put(f"{API}/tenants/users/{new_id}/roles", headers=owner_h,
                             json={"role_codes": ["not_a_role"]})).status_code == 422

    # Duplicate email is rejected.
    assert (await client.post(f"{API}/tenants/users", headers=owner_h,
                              json={"email": "x@guard.co", "full_name": "Dup", "role_codes": ["clerk"]})).status_code == 409

    # The admin actions are audited.
    actions = {e["action"] for e in (await client.get(f"{API}/admin/audit", headers=owner_h)).json()}
    assert "user.created" in actions


async def test_invite_rejects_email_registered_in_another_organisation(
    client: AsyncClient, strong_password: str
) -> None:
    """Emails are unique platform-wide (0032), so an invite cannot claim one."""
    await _owner(client, "Alpha LLP", "taken@alpha.co", strong_password)
    beta_h, _ = await _owner(client, "Beta LLP", "owner@beta.co", strong_password)

    resp = await client.post(
        f"{API}/tenants/users", headers=beta_h,
        json={"email": "taken@alpha.co", "full_name": "Taken", "role_codes": ["associate"]},
    )
    assert resp.status_code == 409, resp.text
    # Must not disclose which organisation holds the address.
    assert "alpha" not in resp.text.lower()
