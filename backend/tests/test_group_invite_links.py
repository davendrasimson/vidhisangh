"""Group invite links: an admin shares vidhisangh.com/join/<code>; anyone with it joins at once."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def _member(client: AsyncClient, pw: str, email: str) -> dict:
    r = await client.post(f"{API}/auth/register", json={"organisation_name": email, "full_name": f"Adv. {email[:4].title()}",
                                                         "email": email, "password": pw, "accept_terms": True})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_invite_link_lets_people_join_even_a_private_group(client: AsyncClient, strong_password: str) -> None:
    admin = await _member(client, strong_password, "bar@example.com")
    g = (await client.post(f"{API}/groups", headers=admin, json={
        "name": "Karnal District Bar Association", "description": "Members of the Karnal bar", "visibility": "private",
    })).json()
    link = (await client.post(f"{API}/groups/{g['id']}/invite-link", headers=admin)).json()
    assert link["url"] == f"https://vidhisangh.com/join/{link['code']}" and len(link["code"]) >= 8
    assert (await client.post(f"{API}/groups/{g['id']}/invite-link", headers=admin)).json() == link  # stable

    # Anyone can see what the link leads to, without signing in.
    preview = (await client.get(f"{API}/groups/invite/{link['code']}")).json()
    assert preview["name"] == "Karnal District Bar Association" and preview["member_count"] == 1

    member = await _member(client, strong_password, "junior@example.com")
    joined = await client.post(f"{API}/groups/invite/{link['code']}/join", headers=member)
    assert joined.status_code == 200 and joined.json()["member_count"] == 2
    assert (await client.post(f"{API}/groups/invite/{link['code']}/join", headers=member)).json()["member_count"] == 2  # idempotent
    mine = (await client.get(f"{API}/groups/mine", headers=member)).json()
    assert [x["name"] for x in mine] == ["Karnal District Bar Association"]

    # Only admins get the link; a reset stops the old one.
    assert (await client.post(f"{API}/groups/{g['id']}/invite-link", headers=member)).status_code == 403
    new = (await client.post(f"{API}/groups/{g['id']}/invite-link?reset=true", headers=admin)).json()
    assert new["code"] != link["code"]
    assert (await client.get(f"{API}/groups/invite/{link['code']}")).status_code == 404
    late = await _member(client, strong_password, "late@example.com")
    assert (await client.post(f"{API}/groups/invite/{link['code']}/join", headers=late)).status_code == 404
