"""Drafting — autosave, versions, DOCX export, filing to the library, isolation."""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> dict:
    resp = await client.post(
        f"{API}/auth/register",
        json={"organisation_name": org, "full_name": "Adv. Draft", "email": email,
              "password": pw, "accept_terms": True},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _doc(text: str, *, bold: bool = False) -> dict:
    marks = [{"type": "bold"}] if bold else []
    return {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 1, "textAlign": "center"},
         "content": [{"type": "text", "text": "IN THE HIGH COURT OF DELHI"}]},
        {"type": "paragraph", "attrs": {"textAlign": "justify"},
         "content": [{"type": "text", "text": text, "marks": marks}]},
        {"type": "table", "content": [{"type": "tableRow", "content": [
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Party"}]}]},
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Counsel"}]}]},
        ]}]},
    ]}


async def test_draft_lifecycle_versions_and_docx(client: AsyncClient, strong_password: str) -> None:
    h = await _user(client, "Drafting LLP", "draft@firm.co", strong_password)

    created = await client.post(f"{API}/drafts", headers=h, json={
        "title": "Bail application — Sharma", "language": "en", "template_id": "bail",
        "content_json": _doc("The applicant seeks regular bail."), "content_html": "<p>…</p>",
        "page": {"size": "A4", "orientation": "portrait", "margins": {"top": 25.4, "right": 25.4, "bottom": 25.4, "left": 25.4}},
    })
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["word_count"] == 13 and draft["version_count"] == 0 and draft["status"] == "draft"

    # Autosave sends only what changed; the word count follows the content.
    saved = await client.patch(f"{API}/drafts/{draft['id']}", headers=h, json={
        "content_json": _doc("The applicant seeks regular bail under Section 439 CrPC.", bold=True),
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["word_count"] == 17 and saved.json()["title"] == draft["title"]

    # Named version, then a change, then restore — restoring snapshots first.
    v1 = await client.post(f"{API}/drafts/{draft['id']}/versions", headers=h, json={"note": "Filed copy"})
    assert v1.status_code == 201 and v1.json()["version_no"] == 1
    await client.patch(f"{API}/drafts/{draft['id']}", headers=h, json={"content_json": _doc("Edited later.")})
    restored = await client.post(f"{API}/drafts/{draft['id']}/versions/{v1.json()['id']}/restore", headers=h)
    assert restored.status_code == 200 and restored.json()["word_count"] == 17
    versions = (await client.get(f"{API}/drafts/{draft['id']}/versions", headers=h)).json()
    assert [v["version_no"] for v in versions] == [2, 1]
    assert versions[0]["note"].startswith("Before restoring v1")

    # DOCX export is real Word structure: heading style, bold run, the table.
    from docx import Document

    exported = await client.get(f"{API}/drafts/{draft['id']}/export.docx", headers=h)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "Bail%20application" in exported.headers["content-disposition"]
    word = Document(io.BytesIO(exported.content))
    assert word.paragraphs[0].style.name == "Heading 1"
    assert word.paragraphs[0].text == "IN THE HIGH COURT OF DELHI"
    assert any(r.bold for r in word.paragraphs[1].runs)
    assert [c.text for c in word.tables[0].rows[0].cells] == ["Party", "Counsel"]
    assert round(word.sections[0].page_width.mm) == 210

    # Listing shows it, without content.
    listed = (await client.get(f"{API}/drafts", headers=h, params={"q": "sharma"})).json()
    assert [d["id"] for d in listed] == [draft["id"]] and "content_json" not in listed[0]

    # Delete is soft and final for the API.
    assert (await client.delete(f"{API}/drafts/{draft['id']}", headers=h)).status_code == 204
    assert (await client.get(f"{API}/drafts/{draft['id']}", headers=h)).status_code == 404


async def test_filing_creates_a_library_document_then_versions_it(client: AsyncClient, strong_password: str) -> None:
    h = await _user(client, "Filing LLP", "file@firm.co", strong_password)
    draft = (await client.post(f"{API}/drafts", headers=h, json={
        "title": "Legal notice: Kumar", "content_json": _doc("Notice text."), "content_html": "<p>Notice text.</p>",
    })).json()

    first = await client.post(f"{API}/drafts/{draft['id']}/file", headers=h, json={"comment": "Sent"})
    assert first.status_code == 200, first.text
    doc = first.json()
    assert doc["name"] == "Legal notice- Kumar.docx" and doc["version_count"] == 1
    assert doc["content_type"].startswith("application/vnd.openxmlformats")
    assert "draft" in doc["tags"]

    # Filing again after an edit adds a version to the same library document.
    await client.patch(f"{API}/drafts/{draft['id']}", headers=h, json={"content_json": _doc("Notice text, revised.")})
    second = await client.post(f"{API}/drafts/{draft['id']}/file", headers=h, json={})
    assert second.status_code == 200 and second.json()["id"] == doc["id"] and second.json()["version_count"] == 2
    assert (await client.get(f"{API}/drafts/{draft['id']}", headers=h)).json()["library_document_id"] == doc["id"]

    # The filed copy downloads as a Word document from the library.
    from docx import Document

    downloaded = await client.get(f"{API}/documents/{doc['id']}/download", headers=h)
    assert downloaded.status_code == 200
    assert "revised" in Document(io.BytesIO(downloaded.content)).paragraphs[1].text


async def test_drafts_are_tenant_isolated(client: AsyncClient, strong_password: str) -> None:
    a = await _user(client, "Firm A", "da@firma.co", strong_password)
    b = await _user(client, "Firm B", "db@firmb.co", strong_password)
    draft = (await client.post(f"{API}/drafts", headers=a, json={"title": "Private", "content_json": _doc("secret")})).json()

    assert (await client.get(f"{API}/drafts/{draft['id']}", headers=b)).status_code == 404
    assert (await client.patch(f"{API}/drafts/{draft['id']}", headers=b, json={"title": "x"})).status_code == 404
    assert (await client.get(f"{API}/drafts/{draft['id']}/export.docx", headers=b)).status_code == 404
    assert (await client.get(f"{API}/drafts", headers=b)).json() == []


async def test_oversized_draft_is_rejected() -> None:
    """Checked at the schema (the HTTP path would log the 9 MB body on failure)."""
    from pydantic import ValidationError

    from app.modules.drafting.schemas import DraftCreate

    huge = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "x" * (9 * 1024 * 1024)}]}]}
    with pytest.raises(ValidationError, match="too large"):
        DraftCreate(title="Huge", content_json=huge)
    DraftCreate(title="Fine", content_json=_doc("small"))  # the normal case validates
