"""Knowledge base tests — CRUD, category/keyword filters, tenant isolation."""

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


async def _add(client: AsyncClient, h: dict, **overrides) -> dict:
    body = {"title": "Bail application template", "category": "template",
            "body": "IN THE COURT OF ...", "practice_area": "Criminal", "tags": ["bail"]}
    body.update(overrides)
    resp = await client.post(f"{API}/knowledge/items", headers=h, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_crud_and_filters(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "KB LLP", "kb@firm.co", strong_password)
    tpl = await _add(client, h)
    await _add(client, h, title="Client onboarding checklist", category="checklist",
               body="1. KYC 2. Engagement letter", practice_area="General", tags=["onboarding"])

    # List summaries omit the body.
    listed = (await client.get(f"{API}/knowledge/items", headers=h)).json()
    assert len(listed) == 2 and "body" not in listed[0]

    # Filters.
    templates = (await client.get(f"{API}/knowledge/items?category=template", headers=h)).json()
    assert [i["id"] for i in templates] == [tpl["id"]]
    hits = (await client.get(f"{API}/knowledge/items?q=KYC", headers=h)).json()
    assert len(hits) == 1 and hits[0]["category"] == "checklist"
    crim = (await client.get(f"{API}/knowledge/items?practice_area=Criminal", headers=h)).json()
    assert len(crim) == 1

    # Detail includes the body; update + delete.
    detail = (await client.get(f"{API}/knowledge/items/{tpl['id']}", headers=h)).json()
    assert detail["body"].startswith("IN THE COURT")
    upd = await client.patch(f"{API}/knowledge/items/{tpl['id']}", headers=h, json={"title": "Bail app v2"})
    assert upd.json()["title"] == "Bail app v2"
    assert (await client.delete(f"{API}/knowledge/items/{tpl['id']}", headers=h)).status_code == 204
    assert len((await client.get(f"{API}/knowledge/items", headers=h)).json()) == 1


async def test_knowledge_tenant_isolation(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _user(client, "Firm A", "ka@firma.co", strong_password)
    b_h, _ = await _user(client, "Firm B", "kb2@firmb.co", strong_password)
    a_item = await _add(client, a_h, title="Firm A precedent")
    assert (await client.get(f"{API}/knowledge/items", headers=b_h)).json() == []
    assert (await client.get(f"{API}/knowledge/items/{a_item['id']}", headers=b_h)).status_code == 404


async def test_resources_and_partial_updates(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Resources LLP", "resources@firm.co", strong_password)
    upload = await client.post(f"{API}/documents", headers=h,
                               files={"file": ("brief.txt", b"Supporting brief", "text/plain")})
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]
    item = await _add(client, h, source_url="https://www.indiacode.nic.in/",
                      reviewed_on="2024-01-01", attachments=[document_id])
    assert item["attachments"] == [document_id]
    assert item["reviewed_on"] == "2024-01-01"
    updated = await client.patch(f"{API}/knowledge/items/{item['id']}", headers=h,
                                 json={"body": "Revised content"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["attachments"] == [document_id]
    assert updated.json()["reviewed_on"] == "2024-01-01"
    assert updated.json()["source_url"] == item["source_url"]
    cleared = await client.patch(f"{API}/knowledge/items/{item['id']}", headers=h,
                                 json={"source_url": None, "reviewed_on": None, "attachments": []})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["attachments"] == []
    assert cleared.json()["reviewed_on"] is None
    assert (await client.get(f"{API}/documents/{document_id}", headers=h)).status_code == 200
    for invalid in ({"source_url": "javascript:alert(1)"}, {"reviewed_on": "2999-01-01"},
                    {"body": None}, {"attachments": None}):
        response = await client.patch(f"{API}/knowledge/items/{item['id']}", headers=h, json=invalid)
        assert response.status_code == 422, response.text


async def test_attachment_isolation(client: AsyncClient, strong_password: str) -> None:
    a, _ = await _user(client, "Attachments A", "attach-a@firm.co", strong_password)
    b, _ = await _user(client, "Attachments B", "attach-b@firm.co", strong_password)
    upload = await client.post(f"{API}/documents", headers=a,
                               files={"file": ("private.txt", b"Private", "text/plain")})
    assert upload.status_code == 201
    doc_id = upload.json()["id"]
    payload = {"title": "Cross tenant", "body": "Attempt", "attachments": [doc_id]}
    assert (await client.post(f"{API}/knowledge/items", headers=b, json=payload)).status_code == 404
    own = await _add(client, b)
    assert (await client.patch(f"{API}/knowledge/items/{own['id']}", headers=b,
                              json={"attachments": [doc_id]})).status_code == 404
    assert (await client.delete(f"{API}/documents/{doc_id}", headers=a)).status_code == 204
    assert (await client.post(f"{API}/knowledge/items", headers=a, json=payload)).status_code == 404
