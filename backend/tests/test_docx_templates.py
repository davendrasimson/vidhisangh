"""Firm Word templates: DOCX import, placeholder forms and tenant isolation."""

from __future__ import annotations

import io
import uuid

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from httpx import AsyncClient

from app.core.storage import MemoryStorage
from app.modules.drafting.docx_import import fill_template, import_docx_template
from app.modules.drafting.models import Draft, DraftTemplate
from app.modules.drafting.schemas import DraftFromTemplate
from app.modules.drafting.service import DraftingService

API = "/api/v1"


def _template_docx() -> bytes:
    word = Document()
    heading = word.add_heading("LEGAL NOTICE", level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph = word.add_paragraph("Client: ")
    paragraph.add_run("{{client_").bold = True
    paragraph.add_run("name}}")
    word.add_paragraph("Facts: {{material facts}}")
    table = word.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Case number"
    table.cell(0, 1).text = "[[case number]]"
    stream = io.BytesIO()
    word.save(stream)
    return stream.getvalue()


def test_docx_import_detects_split_placeholders_and_tables() -> None:
    content, fields, page = import_docx_template(_template_docx())
    assert content["content"][0]["type"] == "heading"
    assert content["content"][-1]["type"] == "table"
    assert [field["key"] for field in fields] == ["client_name", "material_facts", "case_number"]
    assert fields[1]["type"] == "multiline"
    assert page["size"] == "Letter"

    filled = fill_template(
        content,
        fields,
        {
            "client_name": "Asha Sharma",
            "material_facts": "Payment is overdue.",
            "case_number": "CS 42/2026",
        },
    )
    text = str(filled)
    assert "Asha Sharma" in text and "Payment is overdue." in text and "CS 42/2026" in text
    assert "{{client_name}}" not in text


@pytest.mark.asyncio
async def test_template_service_stores_source_and_builds_editable_draft() -> None:
    class FakeSession:
        async def flush(self) -> None: ...
        async def refresh(self, _value: object) -> None: ...

    class FakeRepo:
        def __init__(self) -> None:
            self.templates: dict[uuid.UUID, DraftTemplate] = {}
            self.drafts: dict[uuid.UUID, Draft] = {}

        def add(self, value: object) -> None:
            if isinstance(value, DraftTemplate):
                self.templates[value.id] = value
            elif isinstance(value, Draft):
                self.drafts[value.id] = value

        async def get_template(
            self, tenant_id: uuid.UUID, template_id: uuid.UUID
        ) -> DraftTemplate | None:
            value = self.templates.get(template_id)
            return (
                value
                if value and value.tenant_id == tenant_id and value.deleted_at is None
                else None
            )

        async def list_templates(self, tenant_id: uuid.UUID) -> list[DraftTemplate]:
            return [
                value
                for value in self.templates.values()
                if value.tenant_id == tenant_id and value.deleted_at is None
            ]

    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    storage = MemoryStorage()
    service = DraftingService(FakeSession(), user_id, tenant_id, storage)  # type: ignore[arg-type]
    service.repo = FakeRepo()  # type: ignore[assignment]
    template = await service.create_template(
        data=_template_docx(),
        source_filename="notice.docx",
        name="Office notice",
        description="Firm wording",
        category="Notices",
        language="en",
    )
    assert len(template.fields) == 3
    assert (await service.template_source(template.id))[1].startswith(b"PK")
    draft = await service.create_from_template(
        template.id,
        DraftFromTemplate(
            title="Notice to Sharma",
            values={
                "client_name": "Asha Sharma",
                "material_facts": "Payment is overdue.",
                "case_number": "CS 42/2026",
            },
        ),
    )
    assert draft.template_id == str(template.id)
    assert "Asha Sharma" in str(draft.content_json)
    await service.delete_template(template.id)
    assert await service.templates() == []


async def _user(client: AsyncClient, org: str, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": org,
            "full_name": "Adv. Template",
            "email": email,
            "password": password,
            "accept_terms": True,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_upload_manage_and_create_draft_from_word_template(
    client: AsyncClient, strong_password: str
) -> None:
    first = await _user(client, "Template Firm", "template@firm.co", strong_password)
    second = await _user(client, "Other Firm", "other-template@firm.co", strong_password)
    uploaded = await client.post(
        f"{API}/drafts/templates",
        headers=first,
        data={"name": "Firm legal notice", "category": "Notices", "language": "en"},
        files={
            "file": (
                "legal-notice.docx",
                _template_docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    template = uploaded.json()
    assert len(template["fields"]) == 3
    assert (await client.get(f"{API}/drafts/templates", headers=second)).json() == []
    assert (
        await client.get(f"{API}/drafts/templates/{template['id']}", headers=second)
    ).status_code == 404

    template["fields"][0]["required"] = True
    changed = await client.patch(
        f"{API}/drafts/templates/{template['id']}",
        headers=first,
        json={"description": "Approved office wording", "fields": template["fields"]},
    )
    assert changed.status_code == 200
    assert changed.json()["fields"][0]["required"] is True

    created = await client.post(
        f"{API}/drafts/templates/{template['id']}/drafts",
        headers=first,
        json={
            "title": "Notice to Kumar",
            "values": {
                "client_name": "Asha Sharma",
                "material_facts": "Payment is overdue.",
                "case_number": "CS 42/2026",
            },
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["template_id"] == template["id"]
    assert "Asha Sharma" in str(created.json()["content_json"])

    source = await client.get(f"{API}/drafts/templates/{template['id']}/source.docx", headers=first)
    assert source.status_code == 200 and source.content.startswith(b"PK")
    assert (
        await client.delete(f"{API}/drafts/templates/{template['id']}", headers=first)
    ).status_code == 204
