"""End-to-end authentication flow tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient, email: str, pw: str, org: str = "Acme Legal LLP") -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organisation_name": org,
            "full_name": "Test Advocate",
            "email": email,
            "password": pw,
            "accept_terms": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_register_returns_token_pair(client: AsyncClient, strong_password: str) -> None:
    body = await _register(client, "owner@acme.co", strong_password)
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


async def test_register_rejects_weak_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organisation_name": "Weak Co",
            "full_name": "Weak User",
            "email": "weak@acme.co",
            "password": "password",
            "accept_terms": True,
        },
    )
    assert resp.status_code == 422


async def test_login_success_and_me(client: AsyncClient, strong_password: str) -> None:
    await _register(client, "login@acme.co", strong_password)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@acme.co", "password": strong_password},
    )
    assert resp.status_code == 200, resp.text
    access = resp.json()["access_token"]

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert me.status_code == 200
    data = me.json()
    assert data["email"] == "login@acme.co"
    assert any(r["code"] == "org_admin" for r in data["roles"])


async def test_login_wrong_password_rejected(client: AsyncClient, strong_password: str) -> None:
    await _register(client, "wrong@acme.co", strong_password)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@acme.co", "password": "Wrong!Password#1"},
    )
    assert resp.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_refresh_rotates_and_detects_reuse(client: AsyncClient, strong_password: str) -> None:
    tokens = await _register(client, "rotate@acme.co", strong_password)
    old_refresh = tokens["refresh_token"]

    # First refresh succeeds and returns a new refresh token.
    r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r1.status_code == 200, r1.text
    assert r1.json()["refresh_token"] != old_refresh

    # Presenting the just-rotated token again is a client race (two tabs
    # booting, a reload mid-rotation), not theft: it gets a fresh pair and
    # the first tab's pair keeps working.
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 200, r2.text
    assert r2.json()["refresh_token"] not in (old_refresh, r1.json()["refresh_token"])
    still_valid = await client.post("/api/v1/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]})
    assert still_valid.status_code == 200, still_valid.text


async def test_refresh_reuse_after_grace_revokes_every_session(
    client: AsyncClient, strong_password: str, monkeypatch
) -> None:
    from app.core.config import settings

    tokens = await _register(client, "stolen@acme.co", strong_password)
    old_refresh = tokens["refresh_token"]
    r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r1.status_code == 200

    # No grace: the same reuse now reads as a stolen token.
    monkeypatch.setattr(settings, "REFRESH_REUSE_GRACE_SECONDS", 0)
    import asyncio
    await asyncio.sleep(0.05)  # so the rotation is measurably in the past
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401
    assert r2.json()["title"] == "refresh_reuse_detected"
    # …and the whole family is revoked, including the legitimate successor.
    successor = await client.post("/api/v1/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]})
    assert successor.status_code == 401


async def test_change_password_revokes_sessions(client: AsyncClient, strong_password: str) -> None:
    tokens = await _register(client, "chg@acme.co", strong_password)
    access, refresh = tokens["access_token"], tokens["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {access}"},
        json={"current_password": strong_password, "new_password": "New!Str0ng#2026"},
    )
    assert resp.status_code == 204

    # Old refresh token no longer works after a credential change.
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert reused.status_code == 401


# ─── Global email uniqueness (0032) ─────────────────────────────────
async def test_register_rejects_email_used_by_another_organisation(
    client: AsyncClient, strong_password: str
) -> None:
    """One address = one account platform-wide, so a second org cannot claim it."""
    await _register(client, "dup@acme.co", strong_password, org="First Chambers")

    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organisation_name": "Second Chambers",
            "full_name": "Test Advocate",
            "email": "dup@acme.co",
            "password": strong_password,
            "accept_terms": True,
        },
    )
    assert resp.status_code == 409, resp.text


async def test_rejected_signup_leaves_no_orphan_organisation(
    client: AsyncClient, strong_password: str
) -> None:
    """The email check runs before the tenant is created, so nothing is left behind."""
    await _register(client, "orphan@acme.co", strong_password, org="Only Chambers")
    await client.post(
        "/api/v1/auth/register",
        json={
            "organisation_name": "Ghost Chambers",
            "full_name": "Test Advocate",
            "email": "orphan@acme.co",
            "password": strong_password,
            "accept_terms": True,
        },
    )
    # The original account still signs in, and the rejected org never existed.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "orphan@acme.co", "password": strong_password},
    )
    assert login.status_code == 200, login.text
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.json()["email"] == "orphan@acme.co"


async def test_register_rejects_email_differing_only_by_case(
    client: AsyncClient, strong_password: str
) -> None:
    await _register(client, "case@acme.co", strong_password, org="Case Chambers")

    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "organisation_name": "Other Chambers",
            "full_name": "Test Advocate",
            "email": "CASE@Acme.CO",
            "password": strong_password,
            "accept_terms": True,
        },
    )
    assert resp.status_code == 409, resp.text


async def test_login_needs_no_tenant_slug(client: AsyncClient, strong_password: str) -> None:
    """The old "specify tenant_slug" ambiguity can no longer arise."""
    await _register(client, "solo@acme.co", strong_password, org="Solo Chambers")
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "solo@acme.co", "password": strong_password},
    )
    assert resp.status_code == 200, resp.text
