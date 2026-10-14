"""OAuth/OIDC SSO — provider listing, mock authorize+callback, guards."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _register(client: AsyncClient, org: str, email: str, pw: str) -> None:
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


async def _authorize(client: AsyncClient, login_hint: str) -> str:
    resp = await client.post(
        f"{API}/auth/oauth/mock/authorize",
        json={"redirect_uri": "https://app.test/auth/callback", "login_hint": login_hint},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "code=mock-" in body["authorize_url"]
    return body["state"]


async def test_mock_sso_end_to_end(client: AsyncClient, strong_password: str) -> None:
    await _register(client, "SSO LLP", "sso@firm.co", strong_password)

    # The mock provider is offered outside production; real ones need credentials.
    providers = {p["name"] for p in (await client.get(f"{API}/auth/oauth/providers")).json()}
    assert "mock" in providers and "google" not in providers

    state = await _authorize(client, "sso@firm.co")
    cb = await client.post(
        f"{API}/auth/oauth/mock/callback", json={"code": "mock-abc", "state": state}
    )
    assert cb.status_code == 200, cb.text
    token = cb.json()["access_token"]

    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "sso@firm.co"

    # The SSO login is audited.
    actions = {
        e["action"]
        for e in (await client.get(f"{API}/admin/audit", headers={"Authorization": f"Bearer {token}"})).json()
    }
    assert "auth.sso_login" in actions


async def test_sso_guards(client: AsyncClient, strong_password: str, monkeypatch) -> None:
    await _register(client, "SSO LLP", "known@firm.co", strong_password)

    # Unknown / unconfigured provider.
    assert (await client.post(f"{API}/auth/oauth/google/authorize",
                              json={"redirect_uri": "https://app.test/cb"})).status_code == 404

    # With sign-up turned off, an email without an account is refused.
    from app.core.config import settings
    monkeypatch.setattr(settings, "OAUTH_SIGNUP_ENABLED", False)
    ghost_state = await _authorize(client, "ghost@nobody.co")
    assert (await client.post(f"{API}/auth/oauth/mock/callback",
                              json={"code": "x", "state": ghost_state})).status_code == 403
    monkeypatch.setattr(settings, "OAUTH_SIGNUP_ENABLED", True)

    # A state can be used only once.
    state = await _authorize(client, "known@firm.co")
    assert (await client.post(f"{API}/auth/oauth/mock/callback",
                              json={"code": "x", "state": state})).status_code == 200
    assert (await client.post(f"{API}/auth/oauth/mock/callback",
                              json={"code": "x", "state": state})).status_code == 401

    # An unknown state is rejected.
    assert (await client.post(f"{API}/auth/oauth/mock/callback",
                              json={"code": "x", "state": "nonexistent"})).status_code == 401


async def test_sso_creates_an_account_for_a_new_verified_email(client: AsyncClient, session_factory) -> None:
    """Sign up with Google: no account yet → an individual account, already verified,
    linked to the identity; the next sign-in uses the link."""
    from sqlalchemy import select

    from app.modules.identity.models import OAuthIdentity, User

    state = await _authorize(client, "new.member@gmail.com")
    cb = await client.post(f"{API}/auth/oauth/mock/callback", json={"code": "x", "state": state})
    assert cb.status_code == 200, cb.text
    assert cb.json()["new_account"] is True
    me = (await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {cb.json()['access_token']}"})).json()
    assert me["email"] == "new.member@gmail.com" and me["is_email_verified"] is True
    assert me["full_name"] == "new.member"
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == "new.member@gmail.com"))
        assert user.terms_accepted_at and user.email_verification_delivery_token is None
        link = await session.scalar(select(OAuthIdentity).where(OAuthIdentity.user_id == user.id))
        assert link.provider == "mock"

    again = await client.post(f"{API}/auth/oauth/mock/callback",
                              json={"code": "x", "state": await _authorize(client, "new.member@gmail.com")})
    assert again.status_code == 200 and again.json()["new_account"] is False
