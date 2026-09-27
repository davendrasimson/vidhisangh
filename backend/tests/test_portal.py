"""Client portal tests — firm-side management + client-side token access."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
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


async def _matter(client: AsyncClient, h: dict) -> str:
    return (
        await client.post(f"{API}/matters", headers=h, json={"title": "Acme case", "client_name": "Acme"})
    ).json()["id"]


async def _document(client: AsyncClient, h: dict, content: bytes) -> str:
    return (
        await client.post(
            f"{API}/documents", headers=h,
            files={"file": ("agreement.txt", content, "text/plain")}, data={"name": "Agreement"},
        )
    ).json()["id"]


async def test_portal_end_to_end(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Portal LLP", "firm@firm.co", strong_password)
    mid = await _matter(client, h)
    did = await _document(client, h, b"draft agreement")

    # Firm grants portal access.
    access = await client.post(
        f"{API}/portal/access",
        headers=h,
        json={"matter_id": mid, "client_name": "Acme Ltd", "client_email": "gc@acme.co"},
    )
    assert access.status_code == 201, access.text
    token = access.json()["token"]
    assert token

    # Firm posts an update, requests an approval, shares the document.
    await client.post(
        f"{API}/portal/matters/{mid}/updates", headers=h,
        json={"title": "Filed today", "body": "We filed the petition."},
    )
    approval = await client.post(
        f"{API}/portal/matters/{mid}/approvals", headers=h,
        json={"title": "Approve settlement", "description": "Settle at 10L?"},
    )
    approval_id = approval.json()["id"]
    assert (await client.post(f"{API}/portal/matters/{mid}/documents/{did}", headers=h)).status_code == 204

    # ── Client side (token, no auth header) ──
    view = await client.get(f"{API}/portal/client/{token}")
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["client_name"] == "Acme Ltd"
    assert body["matter_title"] == "Acme case"
    assert [u["title"] for u in body["updates"]] == ["Filed today"]
    assert body["approvals"][0]["status"] == "pending"
    assert [d["name"] for d in body["documents"]] == ["Agreement"]

    # Client approves the request.
    resp = await client.post(
        f"{API}/portal/client/{token}/approvals/{approval_id}/respond",
        json={"approve": True, "note": "Go ahead"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    # Firm sees the approval reflected.
    firm_approvals = await client.get(f"{API}/portal/matters/{mid}/approvals", headers=h)
    assert firm_approvals.json()[0]["status"] == "approved"

    # Client downloads the shared document.
    dl = await client.get(f"{API}/portal/client/{token}/documents/{did}/download")
    assert dl.status_code == 200
    assert dl.content == b"draft agreement"


async def test_invalid_and_revoked_tokens(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Revoke LLP", "rev@firm.co", strong_password)
    mid = await _matter(client, h)
    access = (
        await client.post(
            f"{API}/portal/access", headers=h,
            json={"matter_id": mid, "client_name": "C", "client_email": "c@x.co"},
        )
    ).json()
    token = access["token"]

    # A bogus token is rejected.
    assert (await client.get(f"{API}/portal/client/deadbeef")).status_code == 404

    # A valid token works, then is revoked.
    assert (await client.get(f"{API}/portal/client/{token}")).status_code == 200
    assert (await client.post(f"{API}/portal/access/{access['id']}/revoke", headers=h)).status_code == 200
    assert (await client.get(f"{API}/portal/client/{token}")).status_code == 404


async def test_client_cannot_download_unshared_doc(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Share LLP", "share@firm.co", strong_password)
    mid = await _matter(client, h)
    did = await _document(client, h, b"confidential")
    token = (
        await client.post(
            f"{API}/portal/access", headers=h,
            json={"matter_id": mid, "client_name": "C", "client_email": "c@x.co"},
        )
    ).json()["token"]

    # Document exists but was never shared → client download is denied.
    assert (await client.get(f"{API}/portal/client/{token}/documents/{did}/download")).status_code == 404
