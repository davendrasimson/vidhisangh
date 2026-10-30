"""Client portal hand-off after KYC: one link per open matter, in one call."""

from __future__ import annotations

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import select, update

from app.modules.clients.models import Client, KycStatus
from tests.test_clients import API, _user

pytestmark = pytest.mark.asyncio


async def _verify(session_factory, client_id: str) -> None:
    async with session_factory() as s:
        await s.execute(update(Client).where(Client.id == uuid.UUID(client_id)).values(kyc_status=KycStatus.VERIFIED))
        await s.commit()


async def test_portal_handoff_issues_a_link_per_open_matter(client: AsyncClient, strong_password: str, session_factory) -> None:
    h = await _user(client, "Handoff LLP", "handoff@firm.co", strong_password)
    c = (await client.post(f"{API}/clients", headers=h, json={
        "kind": "individual", "display_name": "Ramesh Kumar", "email": "ramesh@example.in",
    })).json()
    open_ids = []
    for title in ("Ramesh v. State", "Ramesh v. Bank"):
        m = (await client.post(f"{API}/matters", headers=h, json={"title": title, "client_name": "Ramesh Kumar", "client_id": c["id"]})).json()
        open_ids.append(m["id"])
    closed = (await client.post(f"{API}/matters", headers=h, json={"title": "Old one", "client_name": "Ramesh Kumar", "client_id": c["id"]})).json()
    await client.patch(f"{API}/matters/{closed['id']}", headers=h, json={"status": "closed", "stage": "closed"})

    # Not before KYC is verified.
    resp = await client.post(f"{API}/clients/{c['id']}/portal-handoff", headers=h, json={})
    assert resp.status_code == 422, resp.text
    await _verify(session_factory, c["id"])

    resp = await client.post(f"{API}/clients/{c['id']}/portal-handoff", headers=h, json={"message": "See you on Monday."})
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["sent_to_email"] == "ramesh@example.in"
    assert sorted(i["matter_id"] for i in out["items"]) == sorted(open_ids)   # the closed matter is left out
    assert all(i["issued"] and i["url"] and "/portal/" in i["url"] for i in out["items"])

    # Each link opens that matter's portal without logging in.
    for item in out["items"]:
        token = item["url"].rsplit("/", 1)[-1]
        view = await client.get(f"{API}/portal/client/{token}")
        assert view.status_code == 200, view.text
        assert view.json()["matter_number"] == item["matter_number"]

    # Calling again re-lists the live links instead of issuing more.
    again = (await client.post(f"{API}/clients/{c['id']}/portal-handoff", headers=h, json={})).json()
    assert [i["issued"] for i in again["items"]] == [False, False] and all(i["url"] is None for i in again["items"])
    assert again["emailed"] is False

    # A different address issues its own links.
    other = (await client.post(f"{API}/clients/{c['id']}/portal-handoff", headers=h, json={"send_to_email": "son@example.in"})).json()
    assert other["sent_to_email"] == "son@example.in" and all(i["issued"] for i in other["items"])


async def test_portal_handoff_needs_an_email_and_an_open_matter(client: AsyncClient, strong_password: str, session_factory) -> None:
    h = await _user(client, "Handoff Two LLP", "handoff2@firm.co", strong_password)
    c = (await client.post(f"{API}/clients", headers=h, json={"kind": "individual", "display_name": "No Mail"})).json()
    await _verify(session_factory, c["id"])
    resp = await client.post(f"{API}/clients/{c['id']}/portal-handoff", headers=h, json={})
    assert resp.status_code == 422 and "email" in resp.text
    resp = await client.post(f"{API}/clients/{c['id']}/portal-handoff", headers=h, json={"send_to_email": "nomail@example.in"})
    assert resp.status_code == 422 and "open matter" in resp.text
    # Another firm cannot reach this client at all.
    h2 = await _user(client, "Elsewhere LLP", "elsewhere2@firm.co", strong_password)
    assert (await client.post(f"{API}/clients/{c['id']}/portal-handoff", headers=h2, json={})).status_code == 404
