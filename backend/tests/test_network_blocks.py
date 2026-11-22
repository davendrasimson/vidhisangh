"""Member blocking (App Store guideline 1.2) and reporting a group post."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio
API = "/api/v1"


async def _member(client: AsyncClient, pw: str, email: str, name: str) -> tuple[dict, str]:
    r = await client.post(f"{API}/auth/register", json={"organisation_name": f"{name} chambers", "full_name": name,
                                                         "email": email, "password": pw, "accept_terms": True})
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get(f"{API}/auth/me", headers=h)).json()
    return h, me["id"]


async def test_blocking_hides_the_member_both_ways_and_stops_contact(client: AsyncClient, strong_password) -> None:
    rao, rao_id = await _member(client, strong_password, "rao@example.com", "Adv. Rao")
    sen, sen_id = await _member(client, strong_password, "sen@example.com", "Adv. Sen")
    r = await client.post(f"{API}/network/posts", headers=sen, json={"content": "Sen's public note", "visibility": "public"})
    assert r.status_code == 201, r.text
    assert any(p["author_id"] == sen_id for p in (await client.get(f"{API}/network/feed", headers=rao)).json())
    assert any(p["user_id"] == sen_id for p in (await client.get(f"{API}/network/directory", headers=rao)).json())

    # Rao blocks Sen.
    assert (await client.put(f"{API}/network/block/{sen_id}", headers=rao)).status_code == 204
    assert (await client.put(f"{API}/network/block/{sen_id}", headers=rao)).status_code == 204  # idempotent
    assert all(p["author_id"] != sen_id for p in (await client.get(f"{API}/network/feed", headers=rao)).json())
    assert all(p["user_id"] != sen_id for p in (await client.get(f"{API}/network/directory", headers=rao)).json())
    # Sen no longer sees Rao either, and cannot reach Rao's profile, connect or message.
    assert all(p["user_id"] != rao_id for p in (await client.get(f"{API}/network/directory", headers=sen)).json())
    assert (await client.get(f"{API}/network/people/{rao_id}", headers=sen)).status_code == 404
    assert (await client.post(f"{API}/network/connections/{rao_id}", headers=sen, json={"message": "hello"})).status_code == 409
    assert (await client.post(f"{API}/conversations/direct/{rao_id}", headers=sen)).status_code == 404
    assert (await client.post(f"{API}/network/connections/{sen_id}", headers=rao, json={"message": "hi"})).status_code == 409
    # Rao still sees Sen's page (to unblock) and the blocked list.
    me = (await client.get(f"{API}/network/people/{sen_id}", headers=rao)).json()
    assert me["is_blocked"] is True
    assert [p["user_id"] for p in (await client.get(f"{API}/network/blocks", headers=rao)).json()] == [sen_id]
    assert (await client.put(f"{API}/network/block/{rao_id}", headers=rao)).status_code == 422  # not yourself

    # Unblock restores everything.
    assert (await client.delete(f"{API}/network/block/{sen_id}", headers=rao)).status_code == 204
    assert (await client.get(f"{API}/network/blocks", headers=rao)).json() == []
    assert any(p["author_id"] == sen_id for p in (await client.get(f"{API}/network/feed", headers=rao)).json())
    assert (await client.get(f"{API}/network/people/{rao_id}", headers=sen)).status_code == 200


async def test_a_group_post_can_be_reported_and_blocked_authors_vanish_from_the_group(client: AsyncClient, strong_password) -> None:
    rao, rao_id = await _member(client, strong_password, "rao2@example.com", "Adv. Rao")
    sen, sen_id = await _member(client, strong_password, "sen2@example.com", "Adv. Sen")
    g = (await client.post(f"{API}/groups", headers=sen, json={"name": "Bail practice", "description": "x", "group_type": "community", "visibility": "public"})).json()
    assert (await client.post(f"{API}/groups/{g['id']}/join", headers=rao)).status_code in (200, 201)
    post = (await client.post(f"{API}/groups/{g['id']}/posts", headers=sen, json={"content": "An abusive remark"})).json()
    r = await client.post(f"{API}/groups/posts/{post['id']}/report", headers=rao, json={"category": "harassment", "reason": "Personal abuse against a colleague."})
    assert r.status_code == 201 and r.json()["ticket_number"].startswith("VS-")
    assert (await client.post(f"{API}/groups/posts/{post['id']}/report", headers=rao, json={"category": "harassment", "reason": "Personal abuse against a colleague."})).status_code == 422
    assert (await client.post(f"{API}/groups/posts/{post['id']}/report", headers=sen, json={"category": "spam", "reason": "reporting myself?"})).status_code == 422
    assert any(p["id"] == post["id"] for p in (await client.get(f"{API}/groups/{g['id']}/posts", headers=rao)).json())
    assert (await client.put(f"{API}/network/block/{sen_id}", headers=rao)).status_code == 204
    assert all(p["id"] != post["id"] for p in (await client.get(f"{API}/groups/{g['id']}/posts", headers=rao)).json())
