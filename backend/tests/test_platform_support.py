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
    admin_headers = await _register(client, "Operator", "owner@platform.co", strong_password)
    member_headers = await _register(client, "Client Firm", "member@client.co", strong_password)

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
        owner = await session.scalar(select(User).where(User.email == "owner@platform.co"))
        assert owner is not None
        owner.is_superuser = True
        await session.commit()
    admin_headers = await _login(client, "owner@platform.co", strong_password)

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
            f"{API}/platform-admin/users", headers=admin_headers, params={"q": "member@client.co"}
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
    member_headers = await _login(client, "member@client.co", strong_password)

    post = await client.post(
        f"{API}/network/posts",
        headers=member_headers,
        json={"content": "A network post that needs moderator review."},
    )
    assert post.status_code == 201, post.text
    post_id = post.json()["id"]
    report = await client.post(
        f"{API}/network/posts/{post_id}/report",
        headers=admin_headers,
        json={"category": "misinformation", "reason": "The legal claim needs verification."},
    )
    assert report.status_code == 201, report.text
    reported_ticket = next(
        row
        for row in (await client.get(f"{API}/platform-admin/tickets", headers=admin_headers)).json()
        if row["reported_post_id"] == post_id
    )
    assert reported_ticket["reported_user_id"] == member["id"]
    assert reported_ticket["report_context"]["content"] == post.json()["content"]

    restricted = await client.patch(
        f"{API}/platform-admin/users/{member['id']}/posting-restriction",
        headers=admin_headers,
        json={"days": 7, "reason": f"Review under {reported_ticket['ticket_number']}"},
    )
    assert restricted.status_code == 200, restricted.text
    assert restricted.json()["posting_restricted_until"] is not None
    rejected_post = await client.post(
        f"{API}/network/posts", headers=member_headers, json={"content": "Blocked post"}
    )
    assert rejected_post.status_code == 403, rejected_post.text
    removed = await client.post(
        f"{API}/platform-admin/posts/{post_id}/remove",
        headers=admin_headers,
        json={"reason": f"Confirmed under {reported_ticket['ticket_number']}"},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["deleted_at"] is not None

    actions = (await client.get(f"{API}/platform-admin/actions", headers=admin_headers)).json()
    assert {row["action"] for row in actions} >= {
        "member.blocked",
        "member.restored",
        "member.posting_restricted",
        "post.removed",
        "ticket.updated",
    }


async def test_registration_growth_by_day_week_month_in_india_time(
    client: AsyncClient, strong_password: str, session_factory: async_sessionmaker
) -> None:
    """Admin growth view: buckets in IST, comparisons, method/role breakdowns; admins only."""
    from datetime import UTC, datetime

    from app.modules.support.growth import registration_growth
    from app.modules.tenancy.models import Tenant

    await _register(client, "Operator", "op@platform.co", strong_password)
    for i in range(3):
        await _register(client, f"Firm {i}", f"m{i}@firm.co", strong_password)
    member = await _login(client, "m0@firm.co", strong_password)
    assert (await client.get(f"{API}/platform-admin/growth", headers=member)).status_code == 403

    # Fixed clock: Wed 15 Oct 2026, 10:00 IST. m0 joined 00:30 IST today (still 14 Oct in UTC),
    # m1 last week, m2 two months ago.
    when = {
        "m0@firm.co": datetime(2026, 10, 14, 19, 0, tzinfo=UTC),
        "m1@firm.co": datetime(2026, 10, 8, 6, 0, tzinfo=UTC),
        "m2@firm.co": datetime(2026, 8, 20, 6, 0, tzinfo=UTC),
    }
    async with session_factory() as session:
        for user in (await session.scalars(select(User))).all():
            if user.email == "op@platform.co":
                user.is_superuser = True
            elif user.email in when:
                user.created_at = when[user.email]
                (await session.get(Tenant, user.tenant_id)).created_at = when[user.email]
        await session.commit()
        growth = await registration_growth(session, now=datetime(2026, 10, 15, 4, 30, tzinfo=UTC))

    assert growth["total_members"] == 3 and growth["self_signups"] == 3
    k = growth["kpis"]
    assert (k["today"], k["yesterday"], k["this_week"], k["last_week"]) == (1, 0, 1, 1)
    assert (k["this_month"], k["last_month"]) == (2, 0)
    assert growth["daily"][-1] == {"start": "2026-10-15", "label": "15 Oct", "count": 1, "cumulative": 3}
    assert len(growth["daily"]) == 30 and len(growth["weekly"]) == 12 and len(growth["monthly"]) == 12
    assert [m["count"] for m in growth["monthly"][-3:]] == [1, 0, 2]  # Aug, Sep, Oct
    assert growth["monthly"][0]["cumulative"] == 0
    assert growth["by_method"] == [{"key": "email", "label": "Email", "count": 3}]
    assert growth["next_milestone"] == 10 and growth["days_since_last"] == 0
    assert growth["recent"][0]["name"] == "M0"

    admin = await _login(client, "op@platform.co", strong_password)
    live = await client.get(f"{API}/platform-admin/growth", headers=admin)
    assert live.status_code == 200 and live.json()["total_members"] == 3
