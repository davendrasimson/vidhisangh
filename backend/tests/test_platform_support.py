"""Support-ticket and platform-operator workflow tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.identity.models import User

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def _register(client: AsyncClient, org: str, email: str, password: str) -> dict[str, str]:
    response = await client.post(
        f"{API}/auth/register",
        json={
            "organisation_name": org,
            "full_name": email.split("@")[0].title(),
            "email": email,
            "password": password,
            "accept_terms": True,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_ticket_and_platform_moderation(
    client: AsyncClient, strong_password: str, session_factory: async_sessionmaker
) -> None:
    admin_headers = await _register(client, "Operator", "owner@platform.test", strong_password)
    member_headers = await _register(client, "Client Firm", "member@client.test", strong_password)

    created = await client.post(
        f"{API}/support/tickets",
        headers=member_headers,
        json={
            "subject": "Unable to find a filing",
            "description": "The filing is missing from my matter.",
            "category": "data_issue",
            "priority": "high",
            "page_url": "https://vidhisangh.com/app/matters",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["ticket_number"].startswith("VS-")
    assert (
        await client.get(f"{API}/platform-admin/overview", headers=member_headers)
    ).status_code == 403

    async with session_factory() as session:
        owner = await session.scalar(select(User).where(User.email == "owner@platform.test"))
        assert owner is not None
        owner.is_superuser = True
        await session.commit()
    admin_headers = await _login(client, "owner@platform.test", strong_password)

    overview = await client.get(f"{API}/platform-admin/overview", headers=admin_headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["tickets_open"] == 1
    tickets = (await client.get(f"{API}/platform-admin/tickets", headers=admin_headers)).json()
    ticket_id = tickets[0]["id"]
    answered = await client.patch(
        f"{API}/platform-admin/tickets/{ticket_id}",
        headers=admin_headers,
        json={
            "status": "waiting_on_user",
            "assign_to_me": True,
            "response": "Please share the matter number so we can trace it.",
        },
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["messages"][0]["is_staff"] is True

    users = (
        await client.get(
            f"{API}/platform-admin/users", headers=admin_headers, params={"q": "member@client.test"}
        )
    ).json()
    member = users[0]
    blocked = await client.patch(
        f"{API}/platform-admin/users/{member['id']}/status",
        headers=admin_headers,
        json={
            "active": False,
            "reason": "Temporary block requested by the client firm owner.",
        },
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["is_active"] is False
    restored = await client.patch(
        f"{API}/platform-admin/users/{member['id']}/status",
        headers=admin_headers,
        json={
            "active": True,
            "reason": "Identity review completed.",
        },
    )
    assert restored.json()["is_active"] is True
    actions = (await client.get(f"{API}/platform-admin/actions", headers=admin_headers)).json()
    assert {row["action"] for row in actions} >= {
        "member.blocked",
        "member.restored",
        "ticket.updated",
    }
