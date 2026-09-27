"""End-to-end API smoke test: a realistic cross-module user journey.

Exercises identity, network, notifications, profile, groups, messaging and
bookmarks together through the ASGI stack, guarding against cross-module
regressions that per-module tests can miss. (Browser-level e2e via Playwright is
a CI follow-up — no browser tooling in this environment.)
"""

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


async def test_full_cross_module_journey(client: AsyncClient, strong_password: str) -> None:
    a_h, a = await _user(client, "Firm A", "asha@firma.co", strong_password)
    b_h, b = await _user(client, "Firm B", "bilal@firmb.co", strong_password)

    # 1. A publishes a post that mentions B and uses a hashtag.
    post = await client.post(
        f"{API}/network/posts",
        headers=a_h,
        json={
            "content": "Big win in #arbitration today",
            "hashtags": ["arbitration"],
            "mention_ids": [b["id"]],
        },
    )
    assert post.status_code == 201, post.text
    post_id = post.json()["id"]

    # 2. B is notified of the mention.
    notifs = (await client.get(f"{API}/notifications", headers=b_h)).json()
    assert any(n["type"] == "mention" for n in notifs)

    # 3. A opts in to the directory (new identities are hidden — P-10); B views A's
    #    public profile cross-tenant.
    assert (await client.patch(f"{API}/network/me/visibility", headers=a_h, json={"discoverable": True})).status_code == 200
    prof = await client.get(f"{API}/network/people/{a['id']}", headers=b_h)
    assert prof.status_code == 200 and prof.json()["is_self"] is False

    # 4. B sends A a connection request; A is notified, then accepts.
    await client.post(f"{API}/network/connections/{a['id']}", headers=b_h, json={"message": "Let's connect"})
    assert any(n["type"] == "connection_request" for n in (await client.get(f"{API}/notifications", headers=a_h)).json())
    incoming = (await client.get(f"{API}/network/connections/requests", headers=a_h)).json()
    conn_id = incoming[0]["id"]
    accepted = await client.post(f"{API}/network/connections/{conn_id}/accept", headers=a_h)
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    assert any(n["type"] == "connection_accepted" for n in (await client.get(f"{API}/notifications", headers=b_h)).json())

    # 5. A creates a group, invites B, B accepts.
    group = (await client.post(f"{API}/groups", headers=a_h, json={"name": "Arbitration Circle"})).json()
    await client.post(f"{API}/groups/{group['id']}/invite/{b['id']}", headers=a_h)
    assert any(n["type"] == "group_invite" for n in (await client.get(f"{API}/notifications", headers=b_h)).json())
    joined = await client.post(f"{API}/groups/{group['id']}/invitation/accept", headers=b_h)
    assert joined.status_code == 200 and joined.json()["my_status"] == "active"

    # 6. A and B chat.
    conv = (await client.post(f"{API}/conversations/direct/{b['id']}", headers=a_h)).json()
    await client.post(f"{API}/conversations/{conv['id']}/messages", headers=a_h, json={"body": "Congrats!"})
    b_convos = (await client.get(f"{API}/conversations", headers=b_h)).json()
    assert next(c for c in b_convos if c["id"] == conv["id"])["unread_count"] == 1

    # 7. B saves A's post and finds it in the Saved view; the hashtag trends.
    assert (await client.put(f"{API}/network/posts/{post_id}/bookmark", headers=b_h)).status_code == 204
    assert [p["id"] for p in (await client.get(f"{API}/network/bookmarks", headers=b_h)).json()] == [post_id]
    trending = (await client.get(f"{API}/network/trending", headers=b_h)).json()
    assert any(t["tag"] == "arbitration" for t in trending)
