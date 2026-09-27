"""Document management module tests — folders, versioned upload/download,
check-in/out, tenant isolation. Uses the in-memory storage backend."""

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


async def test_upload_download_and_versioning(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Docs LLP", "docs@firm.co", strong_password)

    up = await client.post(
        f"{API}/documents",
        headers=h,
        files={"file": ("brief.txt", b"first version", "text/plain")},
        data={"name": "Opening Brief"},
    )
    assert up.status_code == 201, up.text
    doc = up.json()
    assert doc["name"] == "Opening Brief"
    assert doc["size"] == len(b"first version")
    assert doc["version_count"] == 1
    assert doc["content_type"] == "text/plain"
    assert doc["current_version_id"] is not None
    doc_id = doc["id"]

    # Download the current version.
    dl = await client.get(f"{API}/documents/{doc_id}/download", headers=h)
    assert dl.status_code == 200
    assert dl.content == b"first version"
    assert dl.headers["content-type"].startswith("text/plain")

    # Upload a second version.
    v2 = await client.post(
        f"{API}/documents/{doc_id}/versions",
        headers=h,
        files={"file": ("brief.txt", b"second version is longer", "text/plain")},
        data={"comment": "Revised intro"},
    )
    assert v2.status_code == 201
    assert v2.json()["version_count"] == 2
    assert v2.json()["size"] == len(b"second version is longer")

    assert (await client.get(f"{API}/documents/{doc_id}/download", headers=h)).content == b"second version is longer"

    # Version history is newest-first; the old version is still retrievable.
    versions = (await client.get(f"{API}/documents/{doc_id}/versions", headers=h)).json()
    assert [v["version_no"] for v in versions] == [2, 1]
    v1_id = next(v["id"] for v in versions if v["version_no"] == 1)
    assert (await client.get(f"{API}/documents/versions/{v1_id}/download", headers=h)).content == b"first version"


async def test_folders_and_search(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Folders Co", "fold@firm.co", strong_password)

    folder = await client.post(f"{API}/documents/folders", headers=h, json={"name": "Pleadings"})
    assert folder.status_code == 201
    fid = folder.json()["id"]

    doc = await client.post(
        f"{API}/documents",
        headers=h,
        files={"file": ("ws.pdf", b"%PDF-1.4 written statement", "application/pdf")},
        data={"name": "Written Statement", "folder_id": fid},
    )
    assert doc.status_code == 201
    assert doc.json()["folder_id"] == fid

    # Listed within the folder.
    in_folder = await client.get(f"{API}/documents?folder_id={fid}", headers=h)
    assert [d["id"] for d in in_folder.json()] == [doc.json()["id"]]

    # Name search finds it.
    found = await client.get(f"{API}/documents?q=written", headers=h)
    assert any(d["id"] == doc.json()["id"] for d in found.json())
    assert (await client.get(f"{API}/documents?q=zzzznope", headers=h)).json() == []


async def test_checkout_checkin(client: AsyncClient, strong_password: str) -> None:
    h, me = await _user(client, "Lock Co", "lock@firm.co", strong_password)
    doc_id = (
        await client.post(
            f"{API}/documents", headers=h,
            files={"file": ("a.txt", b"x", "text/plain")}, data={"name": "A"},
        )
    ).json()["id"]

    out = await client.post(f"{API}/documents/{doc_id}/checkout", headers=h)
    assert out.status_code == 200
    assert out.json()["locked_by"] == me["id"]
    assert out.json()["locked_at"] is not None

    # The lock holder can still upload a new version.
    v2 = await client.post(
        f"{API}/documents/{doc_id}/versions", headers=h,
        files={"file": ("a.txt", b"xy", "text/plain")},
    )
    assert v2.status_code == 201

    ci = await client.post(f"{API}/documents/{doc_id}/checkin", headers=h)
    assert ci.status_code == 200 and ci.json()["locked_by"] is None


async def test_documents_tenant_isolation(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _user(client, "Firm A", "da@firma.co", strong_password)
    b_h, _ = await _user(client, "Firm B", "db@firmb.co", strong_password)
    a_doc = (
        await client.post(
            f"{API}/documents", headers=a_h,
            files={"file": ("secret.txt", b"confidential", "text/plain")}, data={"name": "Secret"},
        )
    ).json()

    assert (await client.get(f"{API}/documents", headers=b_h)).json() == []
    assert (await client.get(f"{API}/documents/{a_doc['id']}", headers=b_h)).status_code == 404
    assert (await client.get(f"{API}/documents/{a_doc['id']}/download", headers=b_h)).status_code == 404


async def test_matter_draft_placement(client: AsyncClient, strong_password: str) -> None:
    a, _ = await _user(client, "Draft A", "draft-a@firm.co", strong_password)
    b, _ = await _user(client, "Draft B", "draft-b@firm.co", strong_password)
    matter = await client.post(f"{API}/matters", headers=a,
                              json={"title": "Draft destination", "client_name": "Client"})
    assert matter.status_code == 201
    matter_id = matter.json()["id"]
    for headers, expected in [(a, 201), (b, 404)]:
        response = await client.post(f"{API}/documents", headers=headers,
                                     files={"file": ("draft.txt", b"Draft", "text/plain")},
                                     data={"matter_id": matter_id})
        assert response.status_code == expected, response.text
    listed = await client.get(f"{API}/documents?matter_id={matter_id}", headers=a)
    assert len(listed.json()) == 1
    assert listed.json()[0]["matter_id"] == matter_id
