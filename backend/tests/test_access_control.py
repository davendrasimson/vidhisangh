"""Security audit (Sept 2026) — access-control regressions.

A-5  corpus/news curation is a separate permission; snippets are HTML-safe.
A-6  external roles (client/arbitrator/mediator) hold no practice-data reads.
A-16 every network/groups/messaging/calendar/news/notifications route has an
     RBAC guard; ``X:manage`` implies the CRUD codes so partners can list.
A-17 connections-only posts, shares, comment parents, private-group metadata.
A-32 feature flags are enforced; ``tenant:read`` gates org reads; FK validation.
P-10 directory opt-in.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.main import app
from app.modules.identity.rbac import EXTERNAL_ROLES, SYSTEM_ROLES, expand_permissions
from app.modules.research.repository import sanitise_snippet

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _owner(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
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


NEW_PASSWORD = "Rot4ted!Pass#2026"


async def _invite(client: AsyncClient, owner_h: dict, email: str, roles: list[str]) -> tuple[dict, dict]:
    """Create a user with exactly ``roles`` and sign them in as a normal session.

    Invited users start with ``password_must_change``; the temporary password is
    only returned when ``VS_INVITES_RETURN_TEMP_PASSWORD=true`` (set for the test
    run), so we rotate it through ``/auth/change-password`` and sign in again."""
    created = await client.post(
        f"{API}/tenants/users", headers=owner_h,
        json={"email": email, "full_name": email.split("@")[0].title(), "role_codes": roles},
    )
    assert created.status_code == 201, created.text
    temp = created.json()["temporary_password"]
    assert temp, "run the suite with VS_INVITES_RETURN_TEMP_PASSWORD=true"
    login = await client.post(f"{API}/auth/login", json={"email": email, "password": temp})
    assert login.status_code == 200, login.text
    temp_h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    changed = await client.post(f"{API}/auth/change-password", headers=temp_h,
                                json={"current_password": temp, "new_password": NEW_PASSWORD})
    assert changed.status_code == 204, changed.text
    login = await client.post(f"{API}/auth/login", json={"email": email, "password": NEW_PASSWORD})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return headers, created.json()["user"]


# ─── A-6 / A-16: role reachability ──────────────────────────────────
async def test_external_roles_hold_no_practice_reads() -> None:
    by_code = {r.code: r for r in SYSTEM_ROLES}
    for code in EXTERNAL_ROLES:
        perms = set(by_code[code].permissions)
        assert not perms & {"matter:read", "document:read", "invoice:read", "task:read"}, code
        assert {"message:read", "notification:read"} <= perms, code


async def test_manage_implies_crud_at_seed_time() -> None:
    assert expand_permissions(["matter:manage"]) == [
        "matter:manage", "matter:create", "matter:read", "matter:update", "matter:delete"
    ]
    assert expand_permissions(["*"]) == ["*"]
    by_code = {r.code: r for r in SYSTEM_ROLES}
    for code in ("partner", "corporate_counsel"):
        assert "matter:read" in by_code[code].permissions, code
    # Curation stays with leadership.
    for code in ("student", "associate", "junior_advocate", "client"):
        assert "research:curate" not in by_code[code].permissions
        assert "news:curate" not in by_code[code].permissions
    assert "research:curate" in by_code["managing_partner"].permissions


async def test_every_social_route_is_guarded() -> None:
    """A-16: no route under these prefixes is 'auth only' any more."""
    prefixes = ("/network", "/groups", "/conversations", "/calendar", "/news", "/notifications")
    unguarded: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        api_path = path.removeprefix(API)
        if not api_path.startswith(prefixes):
            continue
        deps = getattr(route, "dependant", None)
        names = {d.call.__qualname__ for d in (deps.dependencies if deps else [])}
        if not any(n.startswith("require_permission") for n in names):
            # The directory opt-in/opt-out endpoints are deliberately available to
            # every authenticated user (privacy control, P-10).
            if api_path in ("/network/me/visibility", "/network/me/directory"):
                continue
            unguarded.append(f"{sorted(route.methods)} {api_path}")
    assert unguarded == [], unguarded


async def test_client_role_cannot_list_matters(client: AsyncClient, strong_password: str) -> None:
    owner_h, _ = await _owner(client, "Scope LLP", "owner@scope.co", strong_password)
    await client.post(f"{API}/matters", headers=owner_h, json={"title": "Secret", "client_name": "X"})
    client_h, _ = await _invite(client, owner_h, "client@scope.co", ["client"])
    assert (await client.get(f"{API}/matters", headers=client_h)).status_code == 403
    assert (await client.get(f"{API}/documents", headers=client_h)).status_code == 403
    assert (await client.get(f"{API}/billing/invoices", headers=client_h)).status_code == 403
    assert (await client.get(f"{API}/calendar/agenda", headers=client_h,
                             params={"start": "2026-01-01T00:00:00Z", "end": "2026-12-31T00:00:00Z"})).status_code == 403
    # …but their own notifications and messaging still work.
    assert (await client.get(f"{API}/notifications", headers=client_h)).status_code == 200
    assert (await client.get(f"{API}/conversations", headers=client_h)).status_code == 200


async def test_partner_and_corporate_counsel_can_list_matters(
    client: AsyncClient, strong_password: str
) -> None:
    owner_h, _ = await _owner(client, "Reach LLP", "owner@reach.co", strong_password)
    for role in ("partner", "corporate_counsel"):
        h, _ = await _invite(client, owner_h, f"{role}@reach.co", [role])
        assert (await client.get(f"{API}/matters", headers=h)).status_code == 200, role
        assert (await client.get(f"{API}/network/feed", headers=h)).status_code == 200, role


async def test_guest_is_read_only(client: AsyncClient, strong_password: str) -> None:
    owner_h, _ = await _owner(client, "Guest LLP", "owner@guest.co", strong_password)
    guest_h, _ = await _invite(client, owner_h, "guest@guest.co", ["guest"])
    assert (await client.get(f"{API}/network/feed", headers=guest_h)).status_code == 200
    assert (await client.get(f"{API}/groups", headers=guest_h)).status_code == 200
    assert (await client.post(f"{API}/network/posts", headers=guest_h, json={"content": "hi"})).status_code == 403
    assert (await client.post(f"{API}/groups", headers=guest_h, json={"name": "Guests"})).status_code == 403
    assert (await client.post(f"{API}/conversations/group", headers=guest_h,
                              json={"title": "x", "participant_ids": [str(__import__("uuid").uuid4())]})).status_code == 403


# ─── A-5: curation + snippet safety ─────────────────────────────────
async def test_students_cannot_write_corpus_or_news(client: AsyncClient, strong_password: str) -> None:
    owner_h, _ = await _owner(client, "Corpus LLP", "owner@corpus.co", strong_password)
    student_h, _ = await _invite(client, owner_h, "student@corpus.co", ["student"])
    judgment = {
        "case_name": "A v. B", "citation": "(2020) 1 SCC 1", "court": "Supreme Court of India",
        "court_level": "supreme_court", "judgment_date": "2020-01-01",
    }
    assert (await client.post(f"{API}/research/judgments", headers=student_h, json=judgment)).status_code == 403
    assert (await client.get(f"{API}/research/judgments", headers=student_h)).status_code == 200
    news = {"title": "Fake news", "source": "X", "published_at": "2026-01-01T00:00:00Z"}
    assert (await client.post(f"{API}/news", headers=student_h, json=news)).status_code == 403
    assert (await client.get(f"{API}/news", headers=student_h)).status_code == 200
    # Leadership can.
    mp_h, _ = await _invite(client, owner_h, "mp@corpus.co", ["managing_partner"])
    created = await client.post(f"{API}/research/judgments", headers=mp_h, json=judgment)
    assert created.status_code == 201, created.text
    assert (await client.post(f"{API}/news", headers=mp_h, json=news)).status_code == 201


async def test_snippet_sanitiser_keeps_only_mark() -> None:
    raw = 'held <script>alert(1)</script> that <mark>seat</mark> & <b>x</b> </mark>'
    out = sanitise_snippet(raw)
    assert out == 'held &lt;script&gt;alert(1)&lt;/script&gt; that <mark>seat</mark> &amp; &lt;b&gt;x&lt;/b&gt; </mark>'
    assert sanitise_snippet(None) is None


# ─── A-17: social visibility ────────────────────────────────────────
async def _connect(client: AsyncClient, a_h: dict, b_h: dict, b_id: str) -> None:
    req = await client.post(f"{API}/network/connections/{b_id}", headers=a_h, json={})
    assert req.status_code == 201, req.text
    acc = await client.post(f"{API}/network/connections/{req.json()['id']}/accept", headers=b_h)
    assert acc.status_code == 200, acc.text


async def test_connections_only_post_is_hidden_from_strangers(
    client: AsyncClient, strong_password: str
) -> None:
    a_h, a = await _owner(client, "Firm A", "a@vis.co", strong_password)
    b_h, b = await _owner(client, "Firm B", "b@vis.co", strong_password)
    s_h, _ = await _owner(client, "Firm S", "s@vis.co", strong_password)
    post = (await client.post(f"{API}/network/posts", headers=a_h,
                              json={"content": "For my circle only", "visibility": "connections"})).json()
    pid = post["id"]
    # Stranger: 404 on read, comments, react, share; the author's page hides it.
    assert (await client.get(f"{API}/network/posts/{pid}", headers=s_h)).status_code == 404
    assert (await client.get(f"{API}/network/posts/{pid}/comments", headers=s_h)).status_code == 404
    assert (await client.post(f"{API}/network/posts/{pid}/comments", headers=s_h, json={"body": "x"})).status_code == 404
    assert (await client.put(f"{API}/network/posts/{pid}/reaction", headers=s_h, json={})).status_code == 404
    assert (await client.post(f"{API}/network/posts/{pid}/share", headers=s_h, json={})).status_code == 404
    assert [p["id"] for p in (await client.get(f"{API}/network/users/{a['id']}/posts", headers=s_h)).json()] == []
    # Connection: can read, but cannot launder it into a public repost.
    await _connect(client, b_h, a_h, a["id"])
    assert (await client.get(f"{API}/network/posts/{pid}", headers=b_h)).status_code == 200
    assert pid in [p["id"] for p in (await client.get(f"{API}/network/users/{a['id']}/posts", headers=b_h)).json()]
    assert (await client.post(f"{API}/network/posts/{pid}/share", headers=b_h, json={})).status_code == 403
    # Author always sees their own.
    assert (await client.get(f"{API}/network/posts/{pid}", headers=a_h)).status_code == 200


async def test_comment_parent_must_belong_to_same_post(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _owner(client, "Firm A", "a@parent.co", strong_password)
    p1 = (await client.post(f"{API}/network/posts", headers=a_h, json={"content": "one"})).json()["id"]
    p2 = (await client.post(f"{API}/network/posts", headers=a_h, json={"content": "two"})).json()["id"]
    c1 = (await client.post(f"{API}/network/posts/{p1}/comments", headers=a_h, json={"body": "root"})).json()["id"]
    bad = await client.post(f"{API}/network/posts/{p2}/comments", headers=a_h, json={"body": "reply", "parent_id": c1})
    assert bad.status_code == 422
    ok = await client.post(f"{API}/network/posts/{p1}/comments", headers=a_h, json={"body": "reply", "parent_id": c1})
    assert ok.status_code == 201


async def test_private_group_shows_reduced_projection_to_non_members(
    client: AsyncClient, strong_password: str
) -> None:
    a_h, _ = await _owner(client, "Firm A", "a@grp.co", strong_password)
    b_h, _ = await _owner(client, "Firm B", "b@grp.co", strong_password)
    group = (await client.post(f"{API}/groups", headers=a_h,
                               json={"name": "Private Bench", "description": "Secret agenda",
                                     "visibility": "private"})).json()
    got = await client.get(f"{API}/groups/{group['id']}", headers=b_h)
    assert got.status_code == 200
    body = got.json()
    assert body["name"] == "Private Bench" and body["member_count"] == 1
    assert "description" not in body and "owner_id" not in body and "post_count" not in body
    # Members (and public groups) still get the full shape.
    full = (await client.get(f"{API}/groups/{group['id']}", headers=a_h)).json()
    assert full["description"] == "Secret agenda" and "owner_id" in full
    # Non-members cannot toggle likes on a private group's posts.
    post = (await client.post(f"{API}/groups/{group['id']}/posts", headers=a_h, json={"content": "hi"})).json()
    assert (await client.delete(f"{API}/groups/posts/{post['id']}/like", headers=b_h)).status_code == 403


# ─── A-32: flags, tenant:read, FK validation ────────────────────────
def _expect(resp, code: int) -> None:  # noqa: ANN001
    assert resp.status_code == code, f"expected {code}, got {resp.status_code}: {resp.text}"


async def test_tenant_read_gates_org_reads(client: AsyncClient, strong_password: str) -> None:
    owner_h, _ = await _owner(client, "Flags LLP", "owner@flags.co", strong_password)
    guest_h, _ = await _invite(client, owner_h, "guest@flags.co", ["guest"])
    client_h, _ = await _invite(client, owner_h, "client@flags.co", ["client"])
    for path in ("/tenants/current", "/feature-flags", "/admin/subscription"):
        assert (await client.get(f"{API}{path}", headers=guest_h)).status_code == 200, path
        assert (await client.get(f"{API}{path}", headers=client_h)).status_code == 403, path


async def test_feature_flag_is_enforced_server_side(client: AsyncClient, strong_password: str) -> None:
    owner_h, _ = await _owner(client, "Flag LLP", "owner@flagoff.co", strong_password)
    other_h, _ = await _owner(client, "Other LLP", "owner@flagon.co", strong_password)
    assert (await client.get(f"{API}/news", headers=owner_h)).status_code == 200
    off = await client.put(f"{API}/admin/feature-flags/legal_news", headers=owner_h, json={"enabled": False})
    assert off.status_code == 200, off.text
    assert (await client.get(f"{API}/news", headers=owner_h)).status_code == 403
    # Other tenants are unaffected.
    assert (await client.get(f"{API}/news", headers=other_h)).status_code == 200


async def test_foreign_keys_must_belong_to_tenant(client: AsyncClient, strong_password: str) -> None:
    a_h, a = await _owner(client, "Firm A", "a@fk.co", strong_password)
    b_h, b = await _owner(client, "Firm B", "b@fk.co", strong_password)
    b_matter = (await client.post(f"{API}/matters", headers=b_h, json={"title": "B's", "client_name": "C"})).json()

    event = {"title": "Meet", "start_at": "2026-10-01T10:00:00Z"}
    _expect(await client.post(f"{API}/calendar/events", headers=a_h,
                              json={**event, "matter_id": b_matter["id"]}), 404)
    _expect(await client.post(f"{API}/calendar/events", headers=a_h,
                              json={**event, "assigned_to": b["id"]}), 404)
    ok = await client.post(f"{API}/calendar/events", headers=a_h, json={**event, "assigned_to": a["id"]})
    assert ok.status_code == 201, ok.text
    upd = await client.patch(f"{API}/calendar/events/{ok.json()['id']}", headers=a_h,
                             json={"matter_id": b_matter["id"]})
    assert upd.status_code == 404, upd.text

    _expect(await client.post(f"{API}/matters", headers=a_h,
                              json={"title": "Matter X", "client_name": "C", "assigned_to": b["id"]}), 404)
    _expect(await client.post(f"{API}/matters", headers=a_h,
                              json={"title": "Matter X", "client_name": "C", "lead_counsel_id": b["id"]}), 404)
    a_matter = (await client.post(f"{API}/matters", headers=a_h,
                                  json={"title": "A's", "client_name": "C", "assigned_to": a["id"]})).json()
    _expect(await client.patch(f"{API}/matters/{a_matter['id']}", headers=a_h,
                               json={"assigned_to": b["id"]}), 404)
    _expect(await client.post(f"{API}/matters/{a_matter['id']}/advocates", headers=a_h,
                              json={"name": "Adv. B", "side": "ours", "user_id": b["id"]}), 404)

    _expect(await client.post(f"{API}/crm/leads", headers=a_h,
                              json={"name": "Lead", "assigned_to": b["id"]}), 404)
    _expect(await client.post(f"{API}/crm/leads", headers=a_h,
                              json={"name": "Lead", "assigned_to": a["id"]}), 201)


# ─── P-10: directory opt-in ─────────────────────────────────────────
async def test_directory_is_opt_in(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _owner(client, "Firm A", "a@dir.co", strong_password)
    b_h, b = await _owner(client, "Firm B", "b@dir.co", strong_password)

    # New sign-ups are listed by default (owner, 1 Nov 2026) and can opt out at once; opting out hides the
    # public page from strangers too.
    me = (await client.get(f"{API}/network/me/identity", headers=b_h)).json()
    assert me["discoverable"] is True and me["audience"] == "everyone"
    off = await client.patch(f"{API}/network/me/visibility", headers=b_h, json={"discoverable": False})
    assert off.status_code == 200 and off.json()["discoverable"] is False
    assert b["id"] not in {p["user_id"] for p in (await client.get(f"{API}/network/directory", headers=a_h)).json()}
    assert (await client.get(f"{API}/network/people/{b['id']}", headers=a_h)).status_code == 404

    # Opt in again → listed and viewable.
    on = await client.patch(f"{API}/network/me/visibility", headers=b_h, json={"discoverable": True})
    assert on.status_code == 200 and on.json()["discoverable"] is True
    assert b["id"] in {p["user_id"] for p in (await client.get(f"{API}/network/directory", headers=a_h)).json()}
    assert (await client.get(f"{API}/network/people/{b['id']}", headers=a_h)).status_code == 200

    # "Remove me" → gone again; the person can still see their own page.
    assert (await client.delete(f"{API}/network/me/directory", headers=b_h)).status_code == 204
    assert b["id"] not in {p["user_id"] for p in (await client.get(f"{API}/network/directory", headers=a_h)).json()}
    assert (await client.get(f"{API}/network/people/{b['id']}", headers=b_h)).status_code == 200
