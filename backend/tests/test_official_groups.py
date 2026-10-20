"""Official community groups: seeded once, public and verified, with a starter post."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.modules.groups import official
from app.modules.groups.models import Group, GroupMembership
from app.modules.identity.models import User

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def test_official_groups_are_seeded_once_and_open_to_join(client: AsyncClient, strong_password: str, session_factory) -> None:
    r = await client.post(f"{API}/auth/register", json={"organisation_name": "Rao Chambers", "full_name": "Adv. Rao",
                                                         "email": "rao@example.com", "password": strong_password, "accept_terms": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    admin_id = (await client.get(f"{API}/auth/me", headers=h)).json()["id"]
    async with session_factory() as s:
        await s.execute(update(User).where(User.email == "rao@example.com").values(is_superuser=True))
        assert await official.seed(s) == {"groups": len(official.GROUPS), "admins": len(official.GROUPS)}
        await s.commit()
    async with session_factory() as s:
        assert await official.seed(s) == {"groups": 0, "admins": 0}
        groups = (await s.scalars(select(Group))).all()
        assert len(groups) == len(official.GROUPS) and all(g.is_verified and g.visibility == "public" for g in groups)
        roles = {m.role for m in await s.scalars(select(GroupMembership).where(GroupMembership.user_id == uuid.UUID(admin_id)))}
        assert roles == {"admin"}

    # A member finds and joins one, and sees the starter post.
    r2 = await client.post(f"{API}/auth/register", json={"organisation_name": "Student", "full_name": "Asha Student",
                                                          "email": "asha@example.com", "password": strong_password, "accept_terms": True})
    h2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    found = (await client.get(f"{API}/groups", headers=h2, params={"limit": 50})).json()
    ask = next(g for g in found if g["slug"] == "ask-a-senior")
    assert (await client.post(f"{API}/groups/{ask['id']}/join", headers=h2)).status_code in (200, 201)
    posts = (await client.get(f"{API}/groups/{ask['id']}/posts", headers=h2)).json()
    assert posts and posts[0]["author_name"] == "VidhiSangh" and "first year of practice" in posts[0]["content"]
