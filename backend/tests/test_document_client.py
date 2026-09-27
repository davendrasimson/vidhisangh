"""Documents and drafts can belong to a client from the client master — or to none."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> dict:
    resp = await client.post(
        f"{API}/auth/register",
        json={"organisation_name": org, "full_name": "Adv. Doc", "email": email, "password": pw, "accept_terms": True},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_documents_and_drafts_link_to_client(client: AsyncClient, strong_password: str) -> None:
    h = await _user(client, "Doc LLP", "doc@firm.co", strong_password)
    c = (await client.post(f"{API}/clients", headers=h, json={"kind": "individual", "display_name": "Priya Sharma"})).json()

    # Upload for a client, and one without any client.
    up = await client.post(f"{API}/documents", headers=h, data={"client_id": c["id"]},
                           files={"file": ("vakalatnama.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert up.status_code == 201, up.text
    assert up.json()["client_id"] == c["id"] and up.json()["client_name"] == "Priya Sharma"
    plain = await client.post(f"{API}/documents", headers=h, data={"name": "office-format.docx"},
                              files={"file": ("office-format.txt", b"x", "text/plain")})
    assert plain.status_code == 201 and plain.json()["client_id"] is None and plain.json()["client_name"] is None

    # Filter by client; the plain one stays out.
    mine = (await client.get(f"{API}/documents", headers=h, params={"client_id": c["id"]})).json()
    assert [d["name"] for d in mine] == ["vakalatnama.pdf"]
    everything = (await client.get(f"{API}/documents", headers=h)).json()
    assert {d["name"] for d in everything} == {"vakalatnama.pdf", "office-format.docx"}
    assert next(d for d in everything if d["name"] == "vakalatnama.pdf")["client_name"] == "Priya Sharma"

    # Link later / unlink via PATCH; absent field leaves it alone.
    linked = await client.patch(f"{API}/documents/{plain.json()['id']}", headers=h, json={"client_id": c["id"]})
    assert linked.json()["client_name"] == "Priya Sharma"
    renamed = await client.patch(f"{API}/documents/{plain.json()['id']}", headers=h, json={"name": "Office format.docx"})
    assert renamed.json()["client_id"] == c["id"]
    unlinked = await client.patch(f"{API}/documents/{plain.json()['id']}", headers=h, json={"client_id": None})
    assert unlinked.json()["client_id"] is None

    # Drafts: created for a client, listed by client, filed to the library with the client.
    d = await client.post(f"{API}/drafts", headers=h, json={"title": "Bail application", "client_id": c["id"]})
    assert d.status_code == 201, d.text
    assert d.json()["client_id"] == c["id"]
    nobody = (await client.post(f"{API}/drafts", headers=h, json={"title": "Firm letterhead"})).json()
    by_client = (await client.get(f"{API}/drafts", headers=h, params={"client_id": c["id"]})).json()
    assert [x["title"] for x in by_client] == ["Bail application"] and by_client[0]["client_name"] == "Priya Sharma"
    assert nobody["client_id"] is None
    filed = await client.post(f"{API}/drafts/{d.json()['id']}/file", headers=h, json={})
    assert filed.status_code in (200, 201), filed.text
    assert filed.json()["client_id"] == c["id"]
    moved = await client.patch(f"{API}/drafts/{nobody['id']}", headers=h, json={"client_id": c["id"]})
    assert moved.json()["client_id"] == c["id"]

    # Another tenant's client cannot be attached.
    other_h = await _user(client, "Other LLP", "other@firm.co", strong_password)
    oc = (await client.post(f"{API}/clients", headers=other_h, json={"kind": "individual", "display_name": "X"})).json()
    bad = await client.post(f"{API}/documents", headers=h, data={"client_id": oc["id"]}, files={"file": ("a.txt", b"a", "text/plain")})
    assert bad.status_code == 404
    assert (await client.post(f"{API}/drafts", headers=h, json={"title": "T", "client_id": oc["id"]})).status_code == 404
