"""Tenant-configured matter fields: validation, masking and reporting."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def _user(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": email.split("@")[0],
            "full_name": "Tenant owner",
            "email": email,
            "password": password,
            "accept_terms": True,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_custom_matter_fields_are_secure_and_reportable(
    client: AsyncClient, strong_password: str
) -> None:
    headers = await _user(client, "fields@example.in", strong_password)
    matter = await client.post(
        f"{API}/matters", headers=headers, json={"title": "Recovery suit", "client_name": "Acme"}
    )
    matter_id = matter.json()["id"]

    section = await client.post(
        f"{API}/matter-fields/sections",
        headers=headers,
        json={"name": "Commercial details", "description": "Firm-specific case data"},
    )
    assert section.status_code == 201, section.text

    amount = await client.post(
        f"{API}/matter-fields/fields",
        headers=headers,
        json={
            "label": "Claim amount",
            "field_type": "amount",
            "section_key": "custom",
            "custom_section_id": section.json()["id"],
            "is_required": True,
        },
    )
    secret = await client.post(
        f"{API}/matter-fields/fields",
        headers=headers,
        json={
            "label": "Settlement authority",
            "field_type": "text",
            "section_key": "client_engagement",
            "is_masked": True,
            "is_reportable": True,
        },
    )
    assert amount.status_code == secret.status_code == 201
    assert secret.json()["is_encrypted"] is True
    assert secret.json()["is_reportable"] is False

    saved = await client.put(
        f"{API}/matter-fields/matters/{matter_id}/values",
        headers=headers,
        json={
            "values": [
                {"field_id": amount.json()["id"], "value": "125000.50"},
                {"field_id": secret.json()["id"], "value": "Up to 90000"},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    by_id = {row["field_id"]: row for row in saved.json()}
    assert by_id[secret.json()["id"]]["value"] is None
    assert by_id[secret.json()["id"]]["display_value"] == "••••••••"

    revealed = await client.get(
        f"{API}/matter-fields/matters/{matter_id}/values/{secret.json()['id']}/reveal",
        headers=headers,
    )
    assert revealed.status_code == 200
    assert revealed.json()["value"] == "Up to 90000"

    report = await client.get(f"{API}/matter-fields/report", headers=headers)
    assert report.status_code == 200
    rows = {row["field_id"]: row for row in report.json()}
    assert rows[amount.json()["id"]]["sum"] == 125000.5
    assert rows[amount.json()["id"]]["completion_rate"] == 1.0
    assert rows[secret.json()["id"]]["sensitive"] is True
    assert rows[secret.json()["id"]]["values"] == []


async def test_custom_fields_are_tenant_isolated(
    client: AsyncClient, strong_password: str
) -> None:
    first = await _user(client, "first-fields@example.in", strong_password)
    second = await _user(client, "second-fields@example.in", strong_password)
    created = await client.post(
        f"{API}/matter-fields/fields",
        headers=first,
        json={"label": "Private classification", "field_type": "text", "section_key": "overview"},
    )
    assert created.status_code == 201
    settings = await client.get(f"{API}/matter-fields/settings", headers=second)
    assert settings.status_code == 200
    assert settings.json()["fields"] == []
