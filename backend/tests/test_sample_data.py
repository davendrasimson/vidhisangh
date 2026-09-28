"""Sample workspace creation is removable without touching user-created data."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_registration_sample_workspace_and_exact_cleanup(
    client: AsyncClient, strong_password: str
) -> None:
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "organisation_name": "Sample Chambers",
            "full_name": "Sample Owner",
            "email": "sample-owner@example.com",
            "password": strong_password,
            "accept_terms": True,
            "add_sample_data": True,
        },
    )
    assert registered.status_code == 201, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    status = await client.get("/api/v1/sample-data", headers=headers)
    assert status.status_code == 200
    assert status.json()["available"] is True
    assert status.json()["counts"]["matters"] == 3

    own_matter = await client.post(
        "/api/v1/matters",
        headers=headers,
        json={"title": "Real user matter", "client_name": "Real client"},
    )
    assert own_matter.status_code == 201

    refused = await client.post(
        "/api/v1/sample-data/delete", headers=headers, json={"confirmed": False}
    )
    assert refused.status_code == 400

    cleared = await client.post(
        "/api/v1/sample-data/delete", headers=headers, json={"confirmed": True}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["available"] is False

    matters = await client.get("/api/v1/matters", headers=headers)
    assert [row["title"] for row in matters.json()] == ["Real user matter"]
    assert (await client.get("/api/v1/documents", headers=headers)).json() == []
