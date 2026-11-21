"""First-party sign-up funnel: anonymous daily counters, shown on Platform admin → Growth."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.modules.funnel.models import FunnelDaily
from app.modules.identity.models import User

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def test_steps_are_counted_per_day_and_reach_the_growth_dashboard(client: AsyncClient, strong_password: str, session_factory) -> None:
    for step in ("landing_view", "landing_view", "register_view", "email_form_opened", "whatsapp_code_requested", "made-up-step"):
        assert (await client.post(f"{API}/funnel/{step}")).status_code == 204  # no login needed
    async with session_factory() as s:
        rows = {r.step: r.count for r in await s.scalars(select(FunnelDaily))}
    assert rows == {"landing_view": 2, "register_view": 1, "email_form_opened": 1, "whatsapp_code_requested": 1}

    await client.post(f"{API}/auth/register", json={"organisation_name": "Rao", "full_name": "Adv. Rao",
                                                    "email": "rao@example.com", "password": strong_password, "accept_terms": True})
    async with session_factory() as s:
        await s.execute(update(User).where(User.email == "rao@example.com").values(is_superuser=True))
        await s.commit()
    # Signed in again so the token carries the platform-admin flag.
    r = await client.post(f"{API}/auth/login", json={"email": "rao@example.com", "password": strong_password})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # A second (non-admin) member so an account counts in the funnel (admins are left out of growth).
    await client.post(f"{API}/auth/register", json={"organisation_name": "Mehta", "full_name": "Adv. Mehta",
                                                    "email": "mehta@example.com", "password": strong_password, "accept_terms": True})
    growth = (await client.get(f"{API}/platform-admin/growth", headers=h)).json()
    week = {x["step"]: x["count"] for x in growth["funnel"]["last_7_days"]}
    assert week == {"landing_view": 2, "register_view": 1, "email_form_opened": 1, "whatsapp_code_requested": 1, "invite_prefilled": 0, "account_created": 1}
    assert [x["step"] for x in growth["funnel"]["last_30_days"]][-1] == "account_created"
