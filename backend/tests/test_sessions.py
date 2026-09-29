"""Active-session / device management — list, mark current, revoke, sign-out-others."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def legacy_body_token_mode(monkeypatch):
    # Device rotation scenarios explicitly exercise the supported body-token
    # client mode; cookie-only browser behavior has separate security tests.
    from app.core.config import settings

    monkeypatch.setattr(settings, "REFRESH_TOKEN_IN_BODY", True)

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _register(client: AsyncClient, org: str, email: str, pw: str) -> str:
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
    return resp.json()["access_token"]


async def _login_refresh(client: AsyncClient, email: str, pw: str) -> str:
    resp = await client.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert resp.status_code == 200, resp.text
    return resp.json()["refresh_token"]


async def test_list_and_revoke_session(client: AsyncClient, strong_password: str) -> None:
    access = await _register(client, "Sess LLP", "sess@firm.co", strong_password)
    h = {"Authorization": f"Bearer {access}"}
    other_refresh = await _login_refresh(client, "sess@firm.co", strong_password)

    sessions = (await client.get(f"{API}/auth/sessions", headers=h)).json()
    assert len(sessions) == 2
    assert sum(1 for s in sessions if s["is_current"]) == 1  # exactly one is this device

    other = next(s for s in sessions if not s["is_current"])
    assert (await client.request("DELETE", f"{API}/auth/sessions/{other['id']}", headers=h)).status_code == 204

    # The revoked session's refresh token no longer works…
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": other_refresh})).status_code == 401
    # …and only the current session remains.
    remaining = (await client.get(f"{API}/auth/sessions", headers=h)).json()
    assert len(remaining) == 1 and remaining[0]["is_current"] is True


async def test_revoke_other_sessions(client: AsyncClient, strong_password: str) -> None:
    access = await _register(client, "Sess LLP", "many@firm.co", strong_password)
    h = {"Authorization": f"Bearer {access}"}
    r2 = await _login_refresh(client, "many@firm.co", strong_password)
    r3 = await _login_refresh(client, "many@firm.co", strong_password)

    assert len((await client.get(f"{API}/auth/sessions", headers=h)).json()) == 3

    revoked = await client.post(f"{API}/auth/sessions/revoke-others", headers=h)
    assert revoked.status_code == 200 and revoked.json()["revoked"] == 2

    # The other devices are signed out; this one keeps working.
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": r2})).status_code == 401
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": r3})).status_code == 401
    left = (await client.get(f"{API}/auth/sessions", headers=h)).json()
    assert len(left) == 1 and left[0]["is_current"] is True


async def test_repeat_login_replaces_same_browser_session(
    client: AsyncClient, strong_password: str
) -> None:
    device_id = "browser-installation-1234567890"
    registered = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": "One Browser LLP",
            "full_name": "Adv. One Browser",
            "email": "browser@firm.co",
            "password": strong_password,
            "accept_terms": True,
            "device_id": device_id,
        },
    )
    assert registered.status_code == 201, registered.text
    old_refresh = registered.json()["refresh_token"]

    signed_in_again = await client.post(
        f"{API}/auth/login",
        json={
            "email": "browser@firm.co",
            "password": strong_password,
            "device_id": device_id,
            "device_label": "Firefox on Linux",
        },
    )
    assert signed_in_again.status_code == 200, signed_in_again.text
    h = {"Authorization": f"Bearer {signed_in_again.json()['access_token']}"}

    sessions = (await client.get(f"{API}/auth/sessions", headers=h)).json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True
    assert sessions[0]["device_label"] == "Firefox on Linux"
    assert (await client.post(
        f"{API}/auth/refresh", json={"refresh_token": old_refresh}
    )).status_code == 401


async def test_refresh_consolidates_pre_device_id_browser_sessions(
    client: AsyncClient, strong_password: str
) -> None:
    access = await _register(client, "Legacy Browser LLP", "legacy-browser@firm.co", strong_password)
    first = await _login_refresh(client, "legacy-browser@firm.co", strong_password)
    latest = await _login_refresh(client, "legacy-browser@firm.co", strong_password)
    h = {"Authorization": f"Bearer {access}"}
    assert len((await client.get(f"{API}/auth/sessions", headers=h)).json()) == 3

    refreshed = await client.post(
        f"{API}/auth/refresh",
        json={
            "refresh_token": latest,
            "device_id": "migrated-browser-1234567890",
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    current = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}
    sessions = (await client.get(f"{API}/auth/sessions", headers=current)).json()
    assert len(sessions) == 1 and sessions[0]["is_current"] is True
    assert (await client.post(
        f"{API}/auth/refresh", json={"refresh_token": first}
    )).status_code == 401
