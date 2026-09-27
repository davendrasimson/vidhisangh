"""Passkeys / WebAuthn — register a passkey, sign in with it, list/remove, guards.

Cryptographic verification is delegated to the mock verifier (see conftest), so
these tests exercise the ceremony flow, challenge lifecycle, credential storage,
and token issuance — not the real attestation/assertion crypto.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _register(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
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


async def _add_passkey(client: AsyncClient, headers: dict, cred_id: str, name: str) -> dict:
    begin = await client.post(f"{API}/auth/passkeys/register/begin", headers=headers)
    assert begin.status_code == 200 and "challenge" in begin.json()
    finish = await client.post(
        f"{API}/auth/passkeys/register/finish", headers=headers,
        json={"name": name, "response": {"credential_id": cred_id, "public_key": f"pk-{cred_id}"}},
    )
    assert finish.status_code == 201, finish.text
    return finish.json()


async def test_register_and_sign_in_with_passkey(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _register(client, "Passkey LLP", "pk@firm.co", strong_password)

    created = await _add_passkey(client, h, "cred-1", "MacBook Touch ID")
    assert created["name"] == "MacBook Touch ID" and created["credential_id"] == "cred-1"

    listed = (await client.get(f"{API}/auth/passkeys", headers=h)).json()
    assert [c["credential_id"] for c in listed] == ["cred-1"]

    # Sign in with the passkey (no password), receiving a token pair.
    begin = await client.post(f"{API}/auth/passkeys/authenticate/begin", json={"email": "pk@firm.co"})
    assert begin.status_code == 200
    assert [c["id"] for c in begin.json()["allowCredentials"]] == ["cred-1"]
    finish = await client.post(
        f"{API}/auth/passkeys/authenticate/finish",
        json={"response": {"credential_id": "cred-1", "signature": "sig"}},
    )
    assert finish.status_code == 200, finish.text
    token = finish.json()["access_token"]
    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "pk@firm.co"

    # Remove the passkey → sign-in is no longer possible.
    assert (await client.request("DELETE", f"{API}/auth/passkeys/{created['id']}", headers=h)).status_code == 204
    assert (await client.post(f"{API}/auth/passkeys/authenticate/begin",
                              json={"email": "pk@firm.co"})).status_code == 404


async def test_passkey_guards(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _register(client, "Guard LLP", "g@firm.co", strong_password)
    await _add_passkey(client, h, "cred-x", "Key")

    # The same credential can't be registered twice.
    await client.post(f"{API}/auth/passkeys/register/begin", headers=h)
    dupe = await client.post(
        f"{API}/auth/passkeys/register/finish", headers=h,
        json={"name": "again", "response": {"credential_id": "cred-x", "public_key": "pk"}},
    )
    assert dupe.status_code == 409

    # Sign-in with an unknown credential is rejected.
    await client.post(f"{API}/auth/passkeys/authenticate/begin", json={"email": "g@firm.co"})
    assert (await client.post(f"{API}/auth/passkeys/authenticate/finish",
                              json={"response": {"credential_id": "ghost", "signature": "s"}})).status_code == 401

    # No passkey for an unknown account.
    assert (await client.post(f"{API}/auth/passkeys/authenticate/begin",
                              json={"email": "nobody@nowhere.co"})).status_code == 404
