"""Tenant provisioning & cross-tenant isolation tests (application layer)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient, org: str, email: str, pw: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organisation_name": org,
            "full_name": "Owner",
            "email": email,
            "password": pw,
            "accept_terms": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_each_registration_creates_isolated_tenant(
    client: AsyncClient, strong_password: str
) -> None:
    t1 = await _register(client, "Firm One", "a@one.co", strong_password)
    t2 = await _register(client, "Firm Two", "b@two.co", strong_password)

    tenant1 = await client.get(
        "/api/v1/tenants/current",
        headers={"Authorization": f"Bearer {t1['access_token']}"},
    )
    tenant2 = await client.get(
        "/api/v1/tenants/current",
        headers={"Authorization": f"Bearer {t2['access_token']}"},
    )
    assert tenant1.status_code == 200 and tenant2.status_code == 200
    body1, body2 = tenant1.json(), tenant2.json()
    assert body1["id"] != body2["id"]
    assert body1["slug"] == "firm-one"
    assert body2["slug"] == "firm-two"


async def test_duplicate_org_names_get_unique_slugs(
    client: AsyncClient, strong_password: str
) -> None:
    t1 = await _register(client, "Same Name", "x@same.co", strong_password)
    t2 = await _register(client, "Same Name", "y@same.co", strong_password)
    s1 = (
        await client.get(
            "/api/v1/tenants/current",
            headers={"Authorization": f"Bearer {t1['access_token']}"},
        )
    ).json()["slug"]
    s2 = (
        await client.get(
            "/api/v1/tenants/current",
            headers={"Authorization": f"Bearer {t2['access_token']}"},
        )
    ).json()["slug"]
    assert s1 != s2


async def test_an_email_cannot_be_shared_by_two_tenants(
    client: AsyncClient, strong_password: str
) -> None:
    """Since 0032 an address belongs to exactly one organisation.

    This replaced an earlier test asserting the opposite: two tenants could
    share an address and login then demanded a ``tenant_slug`` to disambiguate.
    """
    await _register(client, "Org A", "shared@user.co", strong_password)

    second = await client.post(
        "/api/v1/auth/register",
        json={
            "organisation_name": "Org B",
            "full_name": "Owner",
            "email": "shared@user.co",
            "password": strong_password,
            "accept_terms": True,
        },
    )
    assert second.status_code == 409, second.text

    # And the one account it does belong to signs in with no tenant hint.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "shared@user.co", "password": strong_password},
    )
    assert login.status_code == 200, login.text


async def test_health_and_readiness(client: AsyncClient) -> None:
    assert (await client.get("/health")).status_code == 200
