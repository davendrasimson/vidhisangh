"""Groups / communities / firm-pages module tests (cross-tenant global layer)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _register(client: AsyncClient, org: str, email: str, pw: str) -> dict:
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
    return resp.json()


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
    tokens = await _register(client, org, email, pw)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    return headers, me


async def _create_group(client: AsyncClient, headers: dict, **overrides) -> dict:
    body = {"name": "Arbitration Circle", "description": "For arbitration nerds."}
    body.update(overrides)
    resp = await client.post(f"{API}/groups", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_group_makes_creator_owner(client: AsyncClient, strong_password: str) -> None:
    headers, _ = await _user(client, "Firm A", "owner@firma.co", strong_password)
    group = await _create_group(client, headers)
    assert group["my_role"] == "owner"
    assert group["my_status"] == "active"
    assert group["member_count"] == 1
    assert group["slug"]  # auto-derived from name

    mine = await client.get(f"{API}/groups/mine", headers=headers)
    assert any(g["id"] == group["id"] for g in mine.json())


async def test_public_group_join_is_cross_tenant(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "a@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "b@firmb.co", strong_password)
    group = await _create_group(client, h1)

    # User 2 (tenant B) discovers the public group created in tenant A.
    discover = await client.get(f"{API}/groups", headers=h2)
    assert any(g["id"] == group["id"] for g in discover.json())

    join = await client.post(f"{API}/groups/{group['id']}/join", headers=h2)
    assert join.status_code == 200, join.text
    assert join.json()["status"] == "active"

    # Duplicate join is rejected.
    dup = await client.post(f"{API}/groups/{group['id']}/join", headers=h2)
    assert dup.status_code == 409

    got = await client.get(f"{API}/groups/{group['id']}", headers=h2)
    assert got.json()["member_count"] == 2
    assert got.json()["my_role"] == "member"

    members = await client.get(f"{API}/groups/{group['id']}/members", headers=h1)
    assert {m["user_id"] for m in members.json()} >= {me2["id"]}


async def test_private_group_requires_approval(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "priv@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "seeker@firmb.co", strong_password)
    group = await _create_group(client, h1, name="Private Bench", visibility="private")

    req = await client.post(f"{API}/groups/{group['id']}/join", headers=h2)
    assert req.status_code == 200
    assert req.json()["status"] == "pending"

    # Pending members are not counted and not listed as members.
    got = await client.get(f"{API}/groups/{group['id']}", headers=h1)
    assert got.json()["member_count"] == 1
    members = await client.get(f"{API}/groups/{group['id']}/members", headers=h1)
    assert me2["id"] not in {m["user_id"] for m in members.json()}

    # Owner sees and approves the request.
    pending = await client.get(f"{API}/groups/{group['id']}/requests", headers=h1)
    assert any(m["user_id"] == me2["id"] for m in pending.json())
    approve = await client.post(
        f"{API}/groups/{group['id']}/members/{me2['id']}/approve", headers=h1
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "active"

    got = await client.get(f"{API}/groups/{group['id']}", headers=h1)
    assert got.json()["member_count"] == 2


async def test_group_post_and_like(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "poster@firma.co", strong_password)
    h2, _ = await _user(client, "Firm B", "liker@firmb.co", strong_password)
    group = await _create_group(client, h1)
    await client.post(f"{API}/groups/{group['id']}/join", headers=h2)

    post = await client.post(
        f"{API}/groups/{group['id']}/posts",
        headers=h1,
        json={"content": "Welcome to the circle!"},
    )
    assert post.status_code == 201, post.text
    post_id = post.json()["id"]

    like = await client.put(f"{API}/groups/posts/{post_id}/like", headers=h2)
    assert like.status_code == 204

    posts = await client.get(f"{API}/groups/{group['id']}/posts", headers=h2)
    item = next(p for p in posts.json() if p["id"] == post_id)
    assert item["like_count"] == 1
    assert item["liked"] is True

    # Unlike is idempotent-safe and decrements.
    assert (await client.delete(f"{API}/groups/posts/{post_id}/like", headers=h2)).status_code == 204
    posts = await client.get(f"{API}/groups/{group['id']}/posts", headers=h1)
    assert next(p for p in posts.json() if p["id"] == post_id)["like_count"] == 0


async def test_group_post_comments(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "cposter@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "cmenter@firmb.co", strong_password)
    group = await _create_group(client, h1)
    await client.post(f"{API}/groups/{group['id']}/join", headers=h2)

    post_id = (
        await client.post(
            f"{API}/groups/{group['id']}/posts", headers=h1, json={"content": "Discuss?"}
        )
    ).json()["id"]

    comment = await client.post(
        f"{API}/groups/posts/{post_id}/comments", headers=h2, json={"body": "Good point."}
    )
    assert comment.status_code == 201, comment.text
    comment_id = comment.json()["id"]

    # comment_count reflected on the post; comment listed.
    posts = await client.get(f"{API}/groups/{group['id']}/posts", headers=h1)
    assert next(p for p in posts.json() if p["id"] == post_id)["comment_count"] == 1
    listed = await client.get(f"{API}/groups/posts/{post_id}/comments", headers=h1)
    assert [c["body"] for c in listed.json()] == ["Good point."]

    # Author deletes their own comment; count decrements.
    assert (await client.delete(f"{API}/groups/comments/{comment_id}", headers=h2)).status_code == 204
    posts = await client.get(f"{API}/groups/{group['id']}/posts", headers=h1)
    assert next(p for p in posts.json() if p["id"] == post_id)["comment_count"] == 0


async def test_non_member_cannot_comment(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "cin@firma.co", strong_password)
    h2, _ = await _user(client, "Firm B", "cout@firmb.co", strong_password)
    group = await _create_group(client, h1)
    post_id = (
        await client.post(
            f"{API}/groups/{group['id']}/posts", headers=h1, json={"content": "Members only."}
        )
    ).json()["id"]

    resp = await client.post(
        f"{API}/groups/posts/{post_id}/comments", headers=h2, json={"body": "hi"}
    )
    assert resp.status_code == 403


async def test_non_member_cannot_read_or_post(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "in@firma.co", strong_password)
    h2, _ = await _user(client, "Firm B", "out@firmb.co", strong_password)
    group = await _create_group(client, h1)

    assert (await client.get(f"{API}/groups/{group['id']}/posts", headers=h2)).status_code == 403
    resp = await client.post(
        f"{API}/groups/{group['id']}/posts", headers=h2, json={"content": "sneaking in"}
    )
    assert resp.status_code == 403


async def test_moderation_role_and_removal(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "boss@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "mod@firmb.co", strong_password)
    h3, me3 = await _user(client, "Firm C", "member@firmc.co", strong_password)
    group = await _create_group(client, h1)
    await client.post(f"{API}/groups/{group['id']}/join", headers=h2)
    await client.post(f"{API}/groups/{group['id']}/join", headers=h3)

    # A plain member cannot moderate.
    forbidden = await client.delete(
        f"{API}/groups/{group['id']}/members/{me3['id']}", headers=h2
    )
    assert forbidden.status_code == 403

    # Owner promotes user 2 to admin, who may then remove user 3.
    promote = await client.post(
        f"{API}/groups/{group['id']}/members/{me2['id']}/role",
        headers=h1,
        json={"role": "admin"},
    )
    assert promote.status_code == 200
    assert promote.json()["role"] == "admin"

    removed = await client.delete(
        f"{API}/groups/{group['id']}/members/{me3['id']}", headers=h2
    )
    assert removed.status_code == 204
    got = await client.get(f"{API}/groups/{group['id']}", headers=h1)
    assert got.json()["member_count"] == 2  # owner + admin


async def test_invite_accept_flow(client: AsyncClient, strong_password: str) -> None:
    # Every registered user gets a global network identity, so they are
    # invitable from day one.
    h1, _ = await _user(client, "Firm A", "inviter@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "invitee@firmb.co", strong_password)
    group = await _create_group(client, h1, name="Invite Circle", visibility="private")

    invite = await client.post(f"{API}/groups/{group['id']}/invite/{me2['id']}", headers=h1)
    assert invite.status_code == 201, invite.text
    assert invite.json()["status"] == "invited"

    # Duplicate invite rejected; invited members are not yet counted.
    dup = await client.post(f"{API}/groups/{group['id']}/invite/{me2['id']}", headers=h1)
    assert dup.status_code == 409
    got = await client.get(f"{API}/groups/{group['id']}", headers=h1)
    assert got.json()["member_count"] == 1

    # Invitee sees and accepts the invitation.
    inbox = await client.get(f"{API}/groups/invitations", headers=h2)
    assert any(i["group_id"] == group["id"] for i in inbox.json())
    accept = await client.post(f"{API}/groups/{group['id']}/invitation/accept", headers=h2)
    assert accept.status_code == 200
    assert accept.json()["my_status"] == "active"

    got = await client.get(f"{API}/groups/{group['id']}", headers=h1)
    assert got.json()["member_count"] == 2
    members = await client.get(f"{API}/groups/{group['id']}/members", headers=h2)
    assert me2["id"] in {m["user_id"] for m in members.json()}


async def test_invite_guardrails_and_decline(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "gowner@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "ginvitee@firmb.co", strong_password)
    h3, me3 = await _user(client, "Firm C", "gmember@firmc.co", strong_password)
    group = await _create_group(client, h1)

    # A non-member cannot invite.
    forbidden = await client.post(f"{API}/groups/{group['id']}/invite/{me3['id']}", headers=h2)
    assert forbidden.status_code == 403

    # Inviting someone who is already a member conflicts.
    await client.post(f"{API}/groups/{group['id']}/join", headers=h3)
    dup = await client.post(f"{API}/groups/{group['id']}/invite/{me3['id']}", headers=h1)
    assert dup.status_code == 409

    # Invitee declines; the invitation disappears and cannot be accepted.
    await client.post(f"{API}/groups/{group['id']}/invite/{me2['id']}", headers=h1)
    assert (await client.post(f"{API}/groups/{group['id']}/invitation/decline", headers=h2)).status_code == 204
    assert (await client.get(f"{API}/groups/invitations", headers=h2)).json() == []
    missing = await client.post(f"{API}/groups/{group['id']}/invitation/accept", headers=h2)
    assert missing.status_code == 404


async def test_owner_cannot_leave_and_slug_conflict(client: AsyncClient, strong_password: str) -> None:
    headers, _ = await _user(client, "Firm A", "solo@firma.co", strong_password)
    await _create_group(client, headers, slug="taken-slug")

    leave = await client.post(
        f"{API}/groups/{(await _lookup_group(client, headers))['id']}/leave", headers=headers
    )
    assert leave.status_code == 422

    dup = await client.post(
        f"{API}/groups",
        headers=headers,
        json={"name": "Another", "slug": "taken-slug"},
    )
    assert dup.status_code == 409


async def test_firm_page_records_tenant(client: AsyncClient, strong_password: str) -> None:
    headers, me = await _user(client, "Firm A", "firm@firma.co", strong_password)
    group = await _create_group(client, headers, name="Firm A Official", group_type="firm")
    assert group["group_type"] == "firm"
    assert group["tenant_id"] == me["tenant_id"]


async def _lookup_group(client: AsyncClient, headers: dict) -> dict:
    mine = await client.get(f"{API}/groups/mine", headers=headers)
    return mine.json()[0]


async def test_latest_posts_across_my_groups(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm C", "owner@firmc.co", strong_password)
    h2, me2 = await _user(client, "Firm D", "reader@firmd.co", strong_password)
    mine = await _create_group(client, h1, name="Ask a Senior")
    other = await _create_group(client, h1, name="Elsewhere Circle")
    await client.post(f"{API}/groups/{mine['id']}/join", headers=h2)
    for i in range(4):
        assert (await client.post(f"{API}/groups/{mine['id']}/posts", headers=h1, json={"content": f"Post {i}"})).status_code == 201
    await client.post(f"{API}/groups/{other['id']}/posts", headers=h1, json={"content": "Not for the reader"})
    liked = (await client.post(f"{API}/groups/{mine['id']}/posts", headers=h2, json={"content": "The reader's own post"})).json()
    await client.put(f"{API}/groups/posts/{liked['id']}/like", headers=h2)

    resp = await client.get(f"{API}/groups/mine/posts", headers=h2)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 3                                   # 3 by default, newest first
    assert all(i["group_name"] == "Ask a Senior" and i["group_slug"] == mine["slug"] for i in items)
    assert all(i["content"] != "Not for the reader" for i in items)
    everything = (await client.get(f"{API}/groups/mine/posts", headers=h2, params={"limit": 10})).json()
    assert sorted(i["content"] for i in everything) == sorted([f"Post {i}" for i in range(4)] + ["The reader's own post"])
    stamps = [i["created_at"] for i in everything]
    assert stamps == sorted(stamps, reverse=True)
    by_content = {i["content"]: i for i in everything}
    assert by_content["The reader's own post"]["liked"] is True and by_content["Post 0"]["liked"] is False
    # Not a member of anything: an empty card, not an error.
    h3, _ = await _user(client, "Firm E", "lonely@firme.co", strong_password)
    assert (await client.get(f"{API}/groups/mine/posts", headers=h3)).json() == []
