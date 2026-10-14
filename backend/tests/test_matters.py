"""Matters (case management) module tests — tenant-scoped practice management."""

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


async def test_matter_lifecycle(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Rao & Co", "rao@firm.co", strong_password)

    created = await client.post(
        f"{API}/matters",
        headers=h,
        json={
            "title": "Acme v. Beta — arbitration",
            "client_name": "Acme Corp",
            "matter_type": "arbitration",
            "court": "Delhi International Arbitration Centre",
        },
    )
    assert created.status_code == 201, created.text
    matter = created.json()
    assert matter["matter_number"] == "M-0001"
    assert matter["status"] == "open"
    assert matter["parties"] == [] and matter["hearings"] == []
    mid = matter["id"]

    # Appears in the list.
    listed = await client.get(f"{API}/matters", headers=h)
    assert any(m["id"] == mid for m in listed.json())

    # Add a party, a hearing, a task and a note.
    await client.post(
        f"{API}/matters/{mid}/parties", headers=h,
        json={"name": "Acme Corp", "role": "claimant"},
    )
    hearing = await client.post(
        f"{API}/matters/{mid}/hearings", headers=h,
        json={"scheduled_on": "2026-08-01T10:30:00Z", "court": "DIAC", "purpose": "First sitting"},
    )
    assert hearing.status_code == 201, hearing.text
    hid = hearing.json()["id"]
    task = await client.post(
        f"{API}/matters/{mid}/tasks", headers=h,
        json={"title": "File statement of claim", "due_on": "2026-07-25"},
    )
    tid = task.json()["id"]
    await client.post(f"{API}/matters/{mid}/notes", headers=h, json={"body": "Client briefed."})

    detail = (await client.get(f"{API}/matters/{mid}", headers=h)).json()
    assert len(detail["parties"]) == 1
    assert len(detail["hearings"]) == 1
    assert len(detail["tasks"]) == 1
    assert len(detail["notes"]) == 1

    # Progress the matter.
    updated = await client.patch(
        f"{API}/matters/{mid}", headers=h, json={"status": "closed", "stage": "judgment"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "closed" and updated.json()["stage"] == "judgment"

    # Complete the task.
    done = await client.post(f"{API}/matters/tasks/{tid}/done", headers=h)
    assert done.status_code == 200
    assert done.json()["status"] == "done" and done.json()["completed_at"] is not None

    # Record the hearing outcome.
    hu = await client.patch(
        f"{API}/matters/hearings/{hid}", headers=h,
        json={"status": "held", "outcome": "Tribunal constituted", "next_date": "2026-09-01T10:30:00Z"},
    )
    assert hu.status_code == 200 and hu.json()["status"] == "held"

    # Upcoming-hearings calendar feed includes it.
    upcoming = await client.get(f"{API}/matters/hearings/upcoming", headers=h)
    assert any(x["id"] == hid for x in upcoming.json())


async def test_auto_numbering_and_status_filter(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Numbering LLP", "num@firm.co", strong_password)
    n1 = (await client.post(f"{API}/matters", headers=h, json={"title": "One", "client_name": "C1"})).json()
    n2 = (await client.post(f"{API}/matters", headers=h, json={"title": "Two", "client_name": "C2"})).json()
    assert (n1["matter_number"], n2["matter_number"]) == ("M-0001", "M-0002")

    await client.patch(f"{API}/matters/{n2['id']}", headers=h, json={"status": "closed"})
    open_only = await client.get(f"{API}/matters?status=open", headers=h)
    ids = {m["id"] for m in open_only.json()}
    assert n1["id"] in ids and n2["id"] not in ids


async def test_timeline_and_limitation(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Timeline LLP", "tl@firm.co", strong_password)
    matter = await client.post(
        f"{API}/matters", headers=h,
        json={"title": "Time case", "client_name": "C", "limitation_date": "2026-09-30"},
    )
    assert matter.json()["limitation_date"] == "2026-09-30"
    mid = matter.json()["id"]

    await client.post(
        f"{API}/matters/{mid}/hearings", headers=h,
        json={"scheduled_on": "2026-08-01T10:00:00Z", "purpose": "First"},
    )
    tid = (await client.post(f"{API}/matters/{mid}/tasks", headers=h, json={"title": "Draft"})).json()["id"]
    await client.post(f"{API}/matters/tasks/{tid}/done", headers=h)
    await client.post(f"{API}/matters/{mid}/notes", headers=h, json={"body": "Kickoff note"})

    timeline = await client.get(f"{API}/matters/{mid}/timeline", headers=h)
    assert timeline.status_code == 200, timeline.text
    kinds = {e["kind"] for e in timeline.json()}
    assert {"matter", "hearing", "task", "task_done", "note"} <= kinds
    # Newest-first ordering.
    ats = [e["at"] for e in timeline.json()]
    assert ats == sorted(ats, reverse=True)


async def test_matters_are_tenant_isolated(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _user(client, "Firm A", "ma@firma.co", strong_password)
    b_h, _ = await _user(client, "Firm B", "mb@firmb.co", strong_password)
    a_matter = (await client.post(f"{API}/matters", headers=a_h, json={"title": "Secret", "client_name": "X"})).json()

    # Firm B cannot list or fetch Firm A's matter.
    assert all(m["id"] != a_matter["id"] for m in (await client.get(f"{API}/matters", headers=b_h)).json())
    assert (await client.get(f"{API}/matters/{a_matter['id']}", headers=b_h)).status_code == 404


# ─── Indian court record + advocates + eCourts (0033) ───────────────
async def test_matter_carries_indian_court_record(
    client: AsyncClient, strong_password: str
) -> None:
    h, _ = await _user(client, "Court Record LLP", "cr@firm.co", strong_password)
    created = await client.post(
        f"{API}/matters", headers=h,
        json={
            "title": "Ramesh Kumar vs State of Haryana",
            "client_name": "Ramesh Kumar",
            "cnr_number": "HRCH010004562023",
            "case_type": "CRL.A.",
            "case_year": 2023,
            "court_level": "high_court",
            "court_establishment": "Punjab & Haryana High Court",
            "state": "Haryana",
            "district": "Chandigarh",
            "cause_title": "Ramesh Kumar vs State of Haryana",
            "acts": ["Indian Penal Code, 1860"],
            "sections": ["Section 302"],
            "hearing_purpose": "For final arguments",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["cnr_number"] == "HRCH010004562023"
    assert body["court_level"] == "high_court"
    assert body["acts"] == ["Indian Penal Code, 1860"]


async def test_advocates_are_tracked_per_side(
    client: AsyncClient, strong_password: str
) -> None:
    h, _ = await _user(client, "Sides LLP", "sides@firm.co", strong_password)
    matter_id = (await client.post(
        f"{API}/matters", headers=h,
        json={"title": "A vs B", "client_name": "A"},
    )).json()["id"]

    ours = await client.post(
        f"{API}/matters/{matter_id}/advocates", headers=h,
        json={"name": "Adv. Priya Sharma", "side": "ours",
              "role": "arguing_counsel", "is_lead": True,
              "party_represented": "Petitioner"},
    )
    assert ours.status_code == 201, ours.text
    theirs = await client.post(
        f"{API}/matters/{matter_id}/advocates", headers=h,
        json={"name": "Adv. R. Mehta", "side": "opposing",
              "role": "senior_counsel", "party_represented": "Respondent"},
    )
    assert theirs.status_code == 201, theirs.text

    detail = (await client.get(f"{API}/matters/{matter_id}", headers=h)).json()
    by_side = {a["side"]: a for a in detail["advocates"]}
    assert by_side["ours"]["name"] == "Adv. Priya Sharma"
    assert by_side["ours"]["is_lead"] is True
    assert by_side["opposing"]["role"] == "senior_counsel"

    # Opponent history: the same counsel across matters is the point of this.
    hist = await client.get(
        f"{API}/matters/advocates/opposing/Adv. R. Mehta/history", headers=h
    )
    assert hist.status_code == 200, hist.text
    assert any(m["id"] == matter_id for m in hist.json())
    # Our own counsel must never show up as an opponent.
    mine = await client.get(
        f"{API}/matters/advocates/opposing/Adv. Priya Sharma/history", headers=h
    )
    assert mine.json() == []


async def test_ecourts_lookup_unconfigured_is_explicit(
    client: AsyncClient, strong_password: str
) -> None:
    """With no provider we must say so, not invent a case."""
    from app.core.ecourts import set_ecourts_client

    set_ecourts_client(None)   # fall back to the configured default
    h, _ = await _user(client, "NoProvider LLP", "np@firm.co", strong_password)
    resp = await client.post(
        f"{API}/matters/ecourts/lookup", headers=h,
        json={"cnr_number": "DLHC010001232024"},
    )
    assert resp.status_code in (500, 502, 503), resp.text
    assert "not configured" in resp.text.lower()


async def test_ecourts_lookup_rejects_a_malformed_cnr(
    client: AsyncClient, strong_password: str
) -> None:
    from app.core.ecourts import SampleECourtsClient, set_ecourts_client

    set_ecourts_client(SampleECourtsClient())
    try:
        h, _ = await _user(client, "BadCNR LLP", "bad@firm.co", strong_password)
        resp = await client.post(
            f"{API}/matters/ecourts/lookup", headers=h, json={"cnr_number": "12345"},
        )
        assert resp.status_code == 422, resp.text
    finally:
        set_ecourts_client(None)


async def test_ecourts_import_splits_our_side_from_the_opponent(
    client: AsyncClient, strong_password: str
) -> None:
    from app.core.ecourts import SampleECourtsClient, set_ecourts_client

    set_ecourts_client(SampleECourtsClient())
    try:
        h, _ = await _user(client, "Import LLP", "imp@firm.co", strong_password)
        resp = await client.post(
            f"{API}/matters/ecourts/import", headers=h,
            json={
                "cnr_number": "DLHC010001232024",
                "client_name": "Our Client Pvt Ltd",
                "our_side_role": "petitioner",
            },
        )
        assert resp.status_code == 201, resp.text
        matter = resp.json()
        assert matter["cnr_number"] == "DLHC010001232024"
        assert matter["ecourts_source"] == "sample"
        assert matter["ecourts_synced_at"] is not None
        assert matter["court_establishment"]

        sides = {a["side"] for a in matter["advocates"]}
        assert sides == {"ours", "opposing"}, matter["advocates"]
        party_sides = {p["side"] for p in matter["parties"]}
        assert party_sides == {"ours", "opposing"}, matter["parties"]

        # Importing the same CNR twice must be refused, not silently duplicated.
        again = await client.post(
            f"{API}/matters/ecourts/import", headers=h,
            json={"cnr_number": "DLHC010001232024", "client_name": "Our Client Pvt Ltd"},
        )
        assert again.status_code == 409, again.text
    finally:
        set_ecourts_client(None)


async def test_ecourts_refresh_keeps_the_firms_own_fields(
    client: AsyncClient, strong_password: str
) -> None:
    from app.core.ecourts import SampleECourtsClient, set_ecourts_client

    set_ecourts_client(SampleECourtsClient())
    try:
        h, _ = await _user(client, "Refresh LLP", "ref@firm.co", strong_password)
        matter_id = (await client.post(
            f"{API}/matters", headers=h,
            json={"title": "Our own title", "client_name": "Our Client",
                  "cnr_number": "DLHC010009992024"},
        )).json()["id"]

        resp = await client.post(f"{API}/matters/{matter_id}/ecourts/refresh", headers=h)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["title"] == "Our own title"        # never clobbered by a sync
        assert body["client_name"] == "Our Client"
        assert body["court_establishment"]             # registry data did land
        assert body["ecourts_synced_at"] is not None
    finally:
        set_ecourts_client(None)


async def test_ecourts_refresh_without_a_cnr_explains_itself(
    client: AsyncClient, strong_password: str
) -> None:
    from app.core.ecourts import SampleECourtsClient, set_ecourts_client

    set_ecourts_client(SampleECourtsClient())
    try:
        h, _ = await _user(client, "NoCNR LLP", "nocnr@firm.co", strong_password)
        matter_id = (await client.post(
            f"{API}/matters", headers=h, json={"title": "No CNR", "client_name": "X"},
        )).json()["id"]
        resp = await client.post(f"{API}/matters/{matter_id}/ecourts/refresh", headers=h)
        assert resp.status_code == 422, resp.text
        assert "no cnr" in resp.text.lower()
    finally:
        set_ecourts_client(None)


async def test_hearings_keep_the_matters_next_hearing_in_step(client: AsyncClient, strong_password: str) -> None:
    """Adding, moving and completing hearings updates "Next hearing" (FUTURE_DELIVERABLES, 11 Oct 2026)."""
    from datetime import UTC, datetime, timedelta

    h, _ = await _user(client, "Next & Co", "next@firm.co", strong_password)
    mid = (await client.post(f"{API}/matters", headers=h, json={
        "title": "Sharma v. State", "client_name": "R. Sharma", "matter_type": "litigation", "court": "Sessions Court",
    })).json()["id"]

    def at(days: int) -> str:
        return (datetime.now(UTC) + timedelta(days=days)).replace(hour=5, minute=0, second=0, microsecond=0).isoformat()

    async def matter() -> dict:
        return (await client.get(f"{API}/matters/{mid}", headers=h)).json()

    later = (await client.post(f"{API}/matters/{mid}/hearings", headers=h,
                               json={"scheduled_on": at(20), "purpose": "Arguments"})).json()
    m = await matter()
    assert m["next_hearing_date"] == at(20)[:10] and m["hearing_purpose"] == "Arguments"

    soon = (await client.post(f"{API}/matters/{mid}/hearings", headers=h,
                              json={"scheduled_on": at(5), "purpose": "Framing of charge"})).json()
    m = await matter()
    assert m["next_hearing_date"] == at(5)[:10] and m["hearing_purpose"] == "Framing of charge"

    # The listed matters carry it too (the "next 14 days" tile reads this list).
    listed = next(x for x in (await client.get(f"{API}/matters", headers=h)).json() if x["id"] == mid)
    assert listed["next_hearing_date"] == at(5)[:10]

    # Cancelled: the next one follows.
    await client.patch(f"{API}/matters/hearings/{soon['id']}", headers=h, json={"status": "cancelled"})
    m = await matter()
    assert m["next_hearing_date"] == at(20)[:10] and m["hearing_purpose"] == "Arguments"

    # Held, with a next date given by the court: that becomes the next hearing.
    await client.patch(f"{API}/matters/hearings/{later['id']}", headers=h, json={"status": "held", "next_date": at(10)})
    m = await matter()
    assert m["next_hearing_date"] == at(10)[:10] and m["last_hearing_date"] == at(20)[:10]

    # A new hearing before the court's date; the court's date is then withdrawn.
    extra = (await client.post(f"{API}/matters/{mid}/hearings", headers=h,
                               json={"scheduled_on": at(3), "purpose": "Bail"})).json()
    await client.patch(f"{API}/matters/hearings/{later['id']}", headers=h, json={"next_date": None})
    assert (await matter())["next_hearing_date"] == at(3)[:10]

    # That hearing cancelled and nothing else upcoming: its date is cleared.
    await client.patch(f"{API}/matters/hearings/{extra['id']}", headers=h, json={"status": "cancelled"})
    m = await matter()
    assert m["next_hearing_date"] is None and m["hearing_purpose"] is None
