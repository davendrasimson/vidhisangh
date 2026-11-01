"""Professional network module tests (cross-tenant global layer)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _register(client: AsyncClient, org: str, email: str, pw: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
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
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    return headers, me


async def _discoverable(client: AsyncClient, headers: dict) -> None:
    """Opt in to the people directory (new identities are hidden — audit P-10)."""
    resp = await client.patch("/api/v1/network/me/visibility", headers=headers, json={"discoverable": True})
    assert resp.status_code == 200, resp.text


async def test_post_appears_in_feed(client: AsyncClient, strong_password: str) -> None:
    headers, _ = await _user(client, "Firm A", "asha@firma.co", strong_password)
    create = await client.post(
        "/api/v1/network/posts",
        headers=headers,
        json={"content": "Landmark judgment on arbitration today.", "hashtags": ["arbitration"]},
    )
    assert create.status_code == 201, create.text
    feed = await client.get("/api/v1/network/feed", headers=headers)
    assert feed.status_code == 200
    items = feed.json()
    assert len(items) == 1
    assert items[0]["author_name"].startswith("Adv.")
    assert items[0]["like_count"] == 0
    assert items[0]["my_reaction"] is None


async def test_directory_is_cross_tenant(client: AsyncClient, strong_password: str) -> None:
    h1, me1 = await _user(client, "Firm A", "a1@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "b1@firmb.co", strong_password)
    await _discoverable(client, h2)

    # User 1 (tenant A) can discover user 2 (tenant B) in the global directory.
    directory = await client.get("/api/v1/network/directory", headers=h1)
    assert directory.status_code == 200
    ids = {p["user_id"] for p in directory.json()}
    assert me2["id"] in ids
    assert me1["id"] not in ids  # self excluded


async def test_connection_request_accept_flow(client: AsyncClient, strong_password: str) -> None:
    h1, me1 = await _user(client, "Firm A", "req@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "acc@firmb.co", strong_password)

    # 1 → 2 request
    req = await client.post(
        f"/api/v1/network/connections/{me2['id']}", headers=h1, json={"message": "Let's connect."}
    )
    assert req.status_code == 201, req.text
    conn_id = req.json()["id"]

    # duplicate rejected
    dup = await client.post(f"/api/v1/network/connections/{me2['id']}", headers=h1, json={})
    assert dup.status_code == 409

    # 2 sees the incoming request and accepts
    incoming = await client.get("/api/v1/network/connections/requests", headers=h2)
    mine = next(c for c in incoming.json() if c["id"] == conn_id)
    assert mine["requester"]["user_id"] == me1["id"] and mine["requester"]["display_name"]
    accept = await client.post(f"/api/v1/network/connections/{conn_id}/accept", headers=h2)
    assert accept.status_code == 200
    assert accept.json()["status"] == "accepted"

    # both now list it as accepted
    listed = await client.get("/api/v1/network/connections?status=accepted", headers=h1)
    assert len(listed.json()) == 1


async def test_react_and_comment(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "author@firma.co", strong_password)
    h2, _ = await _user(client, "Firm B", "reader@firmb.co", strong_password)

    post_id = (
        await client.post(
            "/api/v1/network/posts", headers=h1, json={"content": "Thoughts on the new evidence rules?"}
        )
    ).json()["id"]

    # Reader reacts (public post is visible cross-tenant).
    react = await client.put(
        f"/api/v1/network/posts/{post_id}/reaction", headers=h2, json={"reaction": "insightful"}
    )
    assert react.status_code == 204

    comment = await client.post(
        f"/api/v1/network/posts/{post_id}/comments", headers=h2, json={"body": "Great analysis."}
    )
    assert comment.status_code == 201, comment.text

    got = (await client.get(f"/api/v1/network/posts/{post_id}", headers=h2)).json()
    assert got["like_count"] == 1
    assert got["comment_count"] == 1

    feed = await client.get("/api/v1/network/feed", headers=h2)
    item = next(i for i in feed.json() if i["id"] == post_id)
    assert item["my_reaction"] == "insightful"

    comments = await client.get(f"/api/v1/network/posts/{post_id}/comments", headers=h2)
    assert comments.json()[0]["body"] == "Great analysis."


async def test_follow_and_unfollow(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "follower@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "followee@firmb.co", strong_password)
    await _discoverable(client, h2)

    assert (await client.put(f"/api/v1/network/follow/{me2['id']}", headers=h1)).status_code == 204
    directory = await client.get("/api/v1/network/directory", headers=h1)
    person = next(p for p in directory.json() if p["user_id"] == me2["id"])
    assert person["is_following"] is True

    assert (await client.delete(f"/api/v1/network/follow/{me2['id']}", headers=h1)).status_code == 204


async def test_bookmark_flow(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "saver@firma.co", strong_password)
    post_id = (
        await client.post(
            "/api/v1/network/posts", headers=h1, json={"content": "Worth re-reading later."}
        )
    ).json()["id"]

    # Save the post.
    assert (await client.put(f"/api/v1/network/posts/{post_id}/bookmark", headers=h1)).status_code == 204

    # It appears in the saved list and is flagged in the feed.
    saved = await client.get("/api/v1/network/bookmarks", headers=h1)
    assert [p["id"] for p in saved.json()] == [post_id]
    assert saved.json()[0]["bookmarked"] is True

    feed = await client.get("/api/v1/network/feed", headers=h1)
    assert next(i for i in feed.json() if i["id"] == post_id)["bookmarked"] is True

    # Unsave; the saved list empties.
    assert (await client.delete(f"/api/v1/network/posts/{post_id}/bookmark", headers=h1)).status_code == 204
    assert (await client.get("/api/v1/network/bookmarks", headers=h1)).json() == []


async def test_mentions(client: AsyncClient, strong_password: str) -> None:
    h1, me1 = await _user(client, "Firm A", "author@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "tagged@firmb.co", strong_password)

    created = await client.post(
        "/api/v1/network/posts",
        headers=h1,
        json={"content": "Great work by the team!", "mention_ids": [me2["id"], me1["id"]]},
    )
    assert created.status_code == 201, created.text
    mentions = created.json()["mentions"]
    # Self-mention is ignored; the tagged colleague is recorded with their name.
    assert [m["user_id"] for m in mentions] == [me2["id"]]
    assert mentions[0]["name"].startswith("Adv.")

    # The mentioned user finds the post in their mentions inbox.
    inbox = await client.get("/api/v1/network/mentions", headers=h2)
    assert inbox.status_code == 200
    assert any(p["id"] == created.json()["id"] for p in inbox.json())

    # A user who was not mentioned has an empty inbox.
    empty = await client.get("/api/v1/network/mentions", headers=h1)
    assert empty.json() == []


async def test_share_repost(client: AsyncClient, strong_password: str) -> None:
    # The original post's created_at is UTC-aware. The repost snapshot must use
    # timestamptz as well (SQLite accepts either; this guards the PostgreSQL bind).
    from app.modules.network.models import Post

    assert Post.__table__.c.shared_created_at.type.timezone is True
    h1, _ = await _user(client, "Firm A", "orig@firma.co", strong_password)
    h2, _ = await _user(client, "Firm B", "resharer@firmb.co", strong_password)

    original = (
        await client.post(
            "/api/v1/network/posts", headers=h1, json={"content": "Original insight."}
        )
    ).json()
    orig_id = original["id"]

    # User 2 reposts with commentary (public post visible cross-tenant).
    share = await client.post(
        f"/api/v1/network/posts/{orig_id}/share", headers=h2, json={"content": "Must read!"}
    )
    assert share.status_code == 201, share.text
    body = share.json()
    assert body["content"] == "Must read!"
    assert body["shared_from_id"] == orig_id
    assert body["shared_content"] == "Original insight."

    # Original's share_count incremented.
    got = (await client.get(f"/api/v1/network/posts/{orig_id}", headers=h1)).json()
    assert got["share_count"] == 1

    # Re-sharing the repost quotes the ultimate original, not the repost.
    reshare = await client.post(
        f"/api/v1/network/posts/{body['id']}/share", headers=h1, json={}
    )
    assert reshare.status_code == 201
    assert reshare.json()["shared_from_id"] == orig_id
    assert reshare.json()["shared_content"] == "Original insight."

    got = (await client.get(f"/api/v1/network/posts/{orig_id}", headers=h1)).json()
    assert got["share_count"] == 2


async def test_trending_hashtags(client: AsyncClient, strong_password: str) -> None:
    h1, _ = await _user(client, "Firm A", "trend@firma.co", strong_password)
    for tags in (["arbitration"], ["arbitration", "evidence"], ["evidence"], ["arbitration"]):
        resp = await client.post(
            "/api/v1/network/posts", headers=h1, json={"content": "x", "hashtags": tags}
        )
        assert resp.status_code == 201

    trending = await client.get("/api/v1/network/trending", headers=h1)
    assert trending.status_code == 200
    tags = trending.json()
    assert tags[0] == {"tag": "arbitration", "count": 3}
    assert {"tag": "evidence", "count": 2} in tags


async def test_public_profile_cross_tenant(client: AsyncClient, strong_password: str) -> None:
    h1, me1 = await _user(client, "Firm A", "pp1@firma.co", strong_password)
    h2, me2 = await _user(client, "Firm B", "pp2@firmb.co", strong_password)
    await _discoverable(client, h2)

    # User 1 (tenant A) can view user 2's (tenant B) public profile.
    other = await client.get(f"/api/v1/network/people/{me2['id']}", headers=h1)
    assert other.status_code == 200, other.text
    assert other.json()["user_id"] == me2["id"]
    assert other.json()["is_self"] is False
    assert other.json()["connection_status"] is None

    mine = await client.get(f"/api/v1/network/people/{me1['id']}", headers=h1)
    assert mine.json()["is_self"] is True


async def test_cannot_connect_to_self(client: AsyncClient, strong_password: str) -> None:
    h1, me1 = await _user(client, "Firm A", "solo@firma.co", strong_password)
    resp = await client.post(f"/api/v1/network/connections/{me1['id']}", headers=h1, json={})
    assert resp.status_code == 422


async def test_home_card_shows_colleagues_in_my_city_and_newest_members(client: AsyncClient, strong_password: str) -> None:
    me, _ = await _user(client, "Me Chambers", "me@prayagraj.law", strong_password)
    near, near_me = await _user(client, "Near Chambers", "near@prayagraj.law", strong_password)
    far, far_me = await _user(client, "Far Chambers", "far@kochi.law", strong_password)
    hidden, _ = await _user(client, "Hidden Chambers", "hidden@prayagraj.law", strong_password)
    for headers, city in ((me, "Prayagraj"), (near, "Prayagraj"), (far, "Kochi"), (hidden, "Prayagraj")):
        assert (await client.put("/api/v1/profiles/me", headers=headers, json={"city": city})).status_code == 200
    # Members are listed by default (1 Nov 2026); "hidden" opts out.
    assert (await client.patch("/api/v1/network/me/visibility", headers=hidden, json={"discoverable": False})).status_code == 200
    # Everyone's identity exists once they have touched the network (hidden opted out of the directory).
    for headers in (me, near, far, hidden):
        assert (await client.get("/api/v1/network/me/identity", headers=headers)).status_code == 200

    home = (await client.get("/api/v1/network/home", headers=me)).json()
    assert home["city"] == "Prayagraj" and home["discoverable"] is True  # listed by default
    assert home["members"] == 4 and home["in_city"] == 3 and home["joined_7d"] == 4
    assert [p["user_id"] for p in home["nearby"]] == [near_me["id"]]          # same city, discoverable
    assert [p["user_id"] for p in home["recent"]] == [far_me["id"]]           # newest others, not repeated
    assert all(p["connection_status"] is None for p in home["nearby"] + home["recent"])

    # Once I have asked to connect, the colleague leaves the suggestions.
    assert (await client.post(f"/api/v1/network/connections/{near_me['id']}", headers=me, json={})).status_code in (200, 201)
    home = (await client.get("/api/v1/network/home", headers=me)).json()
    assert home["nearby"] == []


async def test_members_are_listed_by_default_and_judicial_officers_choose_their_audience(client: AsyncClient, strong_password: str) -> None:
    adv, adv_me = await _user(client, "Adv Chambers", "adv@lko.law", strong_password)
    peer, peer_me = await _user(client, "Peer Chambers", "peer@lko.law", strong_password)
    resp = await client.post("/api/v1/auth/register", json={
        "organisation_name": "Court", "full_name": "Hon'ble Judge", "email": "judge@court.gov", "password": strong_password,
        "accept_terms": True, "professional_role": "judicial_officer"})
    assert resp.status_code == 201, resp.text
    judge = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    judge_me = (await client.get("/api/v1/auth/me", headers=judge)).json()

    # An advocate is listed by default (owner, 1 Nov 2026); a judicial officer is hidden with no audience.
    mine = (await client.get("/api/v1/network/me/visibility", headers=adv)).json()
    assert mine["discoverable"] is True and mine["audience"] == "everyone" and mine["is_judicial"] is False
    theirs = (await client.get("/api/v1/network/me/visibility", headers=judge)).json()
    assert theirs["discoverable"] is False and theirs["audience"] == "none" and theirs["is_judicial"] is True
    listed = {p["user_id"] for p in (await client.get("/api/v1/network/directory", headers=judge)).json()}
    assert adv_me["id"] in listed and peer_me["id"] in listed            # the judge sees everyone
    listed = {p["user_id"] for p in (await client.get("/api/v1/network/directory", headers=adv)).json()}
    assert judge_me["id"] not in listed
    assert (await client.get(f"/api/v1/network/people/{judge_me['id']}", headers=adv)).status_code == 404

    # A judge cannot be "listed" without choosing an audience; choosing one lists them to that audience only.
    r = await client.patch("/api/v1/network/me/visibility", headers=judge, json={"discoverable": True})
    assert r.status_code in (400, 422)
    r = await client.patch("/api/v1/network/me/visibility", headers=judge, json={"audience": "connections"})
    assert r.status_code == 200 and r.json()["discoverable"] is True and r.json()["audience"] == "connections"
    assert judge_me["id"] not in {p["user_id"] for p in (await client.get("/api/v1/network/directory", headers=adv)).json()}
    # ...so the judge connects with the advocate: now the advocate sees them, the peer still does not.
    assert (await client.post(f"/api/v1/network/connections/{adv_me['id']}", headers=judge, json={})).status_code in (200, 201)
    req = next(c for c in (await client.get("/api/v1/network/connections/requests", headers=adv)).json())
    assert (await client.post(f"/api/v1/network/connections/{req['id']}/accept", headers=adv)).status_code in (200, 204)
    assert judge_me["id"] in {p["user_id"] for p in (await client.get("/api/v1/network/directory", headers=adv)).json()}
    assert judge_me["id"] not in {p["user_id"] for p in (await client.get("/api/v1/network/directory", headers=peer)).json()}
    assert (await client.get(f"/api/v1/network/people/{judge_me['id']}", headers=peer)).status_code == 404

    # Bar: members in the same State.
    for headers, state in ((judge, "Uttar Pradesh"), (peer, "Uttar Pradesh")):
        assert (await client.put("/api/v1/profiles/me", headers=headers, json={"state": state, "judicial_state": state})).status_code == 200
    r = await client.patch("/api/v1/network/me/visibility", headers=judge, json={"audience": "bar"})
    assert r.status_code == 200
    assert judge_me["id"] in {p["user_id"] for p in (await client.get("/api/v1/network/directory", headers=peer)).json()}
    # Everyone, then none again.
    assert (await client.patch("/api/v1/network/me/visibility", headers=judge, json={"audience": "none"})).json()["discoverable"] is False
    assert judge_me["id"] not in {p["user_id"] for p in (await client.get("/api/v1/network/directory", headers=peer)).json()}

    # An advocate can still opt out, and back in.
    assert (await client.patch("/api/v1/network/me/visibility", headers=adv, json={"discoverable": False})).json()["discoverable"] is False
    assert adv_me["id"] not in {p["user_id"] for p in (await client.get("/api/v1/network/directory", headers=peer)).json()}
    assert (await client.patch("/api/v1/network/me/visibility", headers=adv, json={"discoverable": True})).json()["audience"] == "everyone"
