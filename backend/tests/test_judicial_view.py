"""Judicial officers: the profession mask takes clients, fees, CRM, the
marketplace and practice analytics out of their permissions, whatever roles
they hold; switching profession re-scopes the session."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.security import TokenType, decode_token
from app.modules.identity.rbac import JUDICIAL_BLOCKED, mask_for_profession


API = "/api/v1"

BLOCKED_GETS = ["/clients", "/billing/invoices", "/crm/leads", "/analytics/overview"]


async def _register(client: AsyncClient, email: str, pw: str, role: str | None) -> dict:
    resp = await client.post(f"{API}/auth/register", json={
        "organisation_name": f"{email} chambers", "full_name": "Hon. Test", "email": email,
        "password": pw, "accept_terms": True, "professional_role": role,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _refresh(client: AsyncClient, tokens: dict) -> dict:
    resp = await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]},
                             headers={"x-requested-with": "VidhiSangh"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _claims(tokens: dict) -> dict:
    return decode_token(tokens["access_token"], expected_type=TokenType.ACCESS)


def _h(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_mask_rules() -> None:
    full = {"matter:read", "client:read", "invoice:manage", "timeentry:create", "lead:read",
            "marketplace:read", "analytics:view", "research:use"}
    assert mask_for_profession(full, "judicial_officer") == {"matter:read", "research:use"}
    # Advocates, retired judicial officers and profile-less users are untouched.
    for role in ("advocate", "retired_judicial_officer", None):
        assert mask_for_profession(full, role) == full
    # Platform staff keep the wildcard.
    assert mask_for_profession({"*"}, "judicial_officer") == {"*"}
    assert "billing:manage" not in JUDICIAL_BLOCKED  # their own subscription stays theirs


@pytest.mark.asyncio
async def test_judicial_officer_is_hard_blocked(client: AsyncClient, strong_password: str) -> None:
    tokens = await _register(client, "judge@courts.in", strong_password, "judicial_officer")
    claims = _claims(tokens)
    assert claims["jud"] is True
    assert not set(claims["scopes"]) & JUDICIAL_BLOCKED
    assert {"matter:read", "hearing:manage", "research:use", "document:read"} <= set(claims["scopes"])

    h = _h(tokens)
    for path in BLOCKED_GETS:
        assert (await client.get(f"{API}{path}", headers=h)).status_code == 403, path
    assert (await client.get(f"{API}/matters", headers=h)).status_code == 200

    # A refreshed token is masked too.
    assert not set(_claims(await _refresh(client, tokens))["scopes"]) & JUDICIAL_BLOCKED

    # Cannot mint an API key for a blocked scope.
    made = await client.post(f"{API}/api-keys", headers=h, json={
        "name": "x", "scopes": ["invoice:read"], "expires_at": (datetime.now(UTC) + timedelta(days=5)).isoformat()})
    assert made.status_code == 422, made.text


@pytest.mark.asyncio
async def test_advocate_and_retired_judge_keep_practice(client: AsyncClient, strong_password: str) -> None:
    for email, role in (("adv@bar.in", "advocate"), ("retd@bar.in", "retired_judicial_officer")):
        tokens = await _register(client, email, strong_password, role)
        assert "jud" not in _claims(tokens)
        assert JUDICIAL_BLOCKED <= set(_claims(tokens)["scopes"])
        for path in BLOCKED_GETS:
            assert (await client.get(f"{API}{path}", headers=_h(tokens))).status_code == 200, path


@pytest.mark.asyncio
async def test_switching_profession_rescopes_the_session(client: AsyncClient, strong_password: str) -> None:
    tokens = await _register(client, "switch@bar.in", strong_password, "advocate")
    key = await client.post(f"{API}/api-keys", headers=_h(tokens), json={
        "name": "bot", "scopes": ["invoice:read", "matter:read"],
        "expires_at": (datetime.now(UTC) + timedelta(days=5)).isoformat()})
    assert key.status_code == 201, key.text
    key_h = {"Authorization": f"Bearer {key.json()['key']}"}
    assert (await client.get(f"{API}/billing/invoices", headers=key_h)).status_code == 200

    # Elevated to the bench: the existing key loses its blocked scopes at once.
    saved = await client.put(f"{API}/profiles/me", headers=_h(tokens), json={"professional_role": "judicial_officer"})
    assert saved.status_code == 200, saved.text
    assert (await client.get(f"{API}/billing/invoices", headers=key_h)).status_code == 403
    assert (await client.get(f"{API}/matters", headers=key_h)).status_code == 200

    # The next refresh carries the judicial view and the mask.
    judge = await _refresh(client, tokens)
    assert _claims(judge)["jud"] is True
    assert (await client.get(f"{API}/billing/invoices", headers=_h(judge))).status_code == 403

    # And back again.
    assert (await client.put(f"{API}/profiles/me", headers=_h(judge), json={"professional_role": "advocate"})).status_code == 200
    adv = await _refresh(client, judge)
    assert "jud" not in _claims(adv)
    assert (await client.get(f"{API}/billing/invoices", headers=_h(adv))).status_code == 200
