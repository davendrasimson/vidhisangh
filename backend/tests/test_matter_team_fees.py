"""Matters: client-master link, dated team with hand-overs and bulk transfer,
fee arrangements with milestones, automatic fee events, counsel rate cards."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _admin(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
    resp = await client.post(
        f"{API}/auth/register",
        json={"organisation_name": org, "full_name": f"Adv. {email.split('@')[0].title()}",
              "email": email, "password": pw, "accept_terms": True},
    )
    assert resp.status_code == 201, resp.text
    h = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = (await client.get(f"{API}/auth/me", headers=h)).json()
    return h, me


async def _colleague(client: AsyncClient, h: dict, name: str, email: str, pw: str) -> dict:
    """Invite a second user into the same organisation."""
    resp = await client.post(
        f"{API}/tenants/users", headers=h,
        json={"full_name": name, "email": email, "role_codes": ["org_admin"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    user = body["user"]
    # Accept the invitation link (no temporary password since the 2026-09 hardening).
    invite_token = body["invitation_url"].rsplit("/", 1)[-1].split("?", 1)[0]
    accepted = await client.post(f"{API}/auth/reset-password", json={"token": invite_token, "new_password": pw})
    assert accepted.status_code == 204, accepted.text
    user["_password"] = pw
    return user


async def _login(client: AsyncClient, user: dict) -> dict:
    resp = await client.post(f"{API}/auth/login", json={"email": user["email"], "password": user["_password"]})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_matter_links_to_client_master(client: AsyncClient, strong_password: str) -> None:
    h, me = await _admin(client, "Link LLP", "link@firm.co", strong_password)
    c = (await client.post(f"{API}/clients", headers=h, json={
        "kind": "business", "display_name": "Sharma Traders", "gstin": "07AAACS1234B1Z2", "state": "Delhi",
    })).json()

    # Pick from the master: the name comes from the client record.
    m = await client.post(f"{API}/matters", headers=h, json={
        "title": "Sharma Traders v. Union of India", "client_id": c["id"], "lead_counsel_id": me["id"],
    })
    assert m.status_code == 201, m.text
    body = m.json()
    assert body["client_id"] == c["id"] and body["client_name"] == "Sharma Traders"
    assert body["lead_counsel_id"] == me["id"] and body["lead_counsel_name"] == me["full_name"]
    assert [t["role"] for t in body["team"]] == ["lead_counsel"]

    # Neither a client nor a name is an error; a typed name still works (quick intake).
    assert (await client.post(f"{API}/matters", headers=h, json={"title": "Nameless"})).status_code == 422
    quick = await client.post(f"{API}/matters", headers=h, json={"title": "Quick", "client_name": "Walk-in"})
    assert quick.status_code == 201 and quick.json()["client_id"] is None

    # Matters for a client, from the client's side.
    by_client = await client.get(f"{API}/matters", headers=h, params={"client_id": c["id"]})
    assert [x["id"] for x in by_client.json()] == [body["id"]]

    # Linking later refreshes the name; unlinking keeps it.
    upd = await client.patch(f"{API}/matters/{quick.json()['id']}", headers=h, json={"client_id": c["id"]})
    assert upd.json()["client_name"] == "Sharma Traders"
    unl = await client.patch(f"{API}/matters/{quick.json()['id']}", headers=h, json={"client_id": None})
    assert unl.json()["client_id"] is None and unl.json()["client_name"] == "Sharma Traders"


async def test_team_roles_handover_and_transfer(client: AsyncClient, strong_password: str) -> None:
    h, me = await _admin(client, "Team LLP", "lead@team.co", strong_password)
    x = await _colleague(client, h, "Adv. X Mehta", "x@team.co", strong_password)
    y = await _colleague(client, h, "Adv. Y Rao", "y@team.co", strong_password)
    people = (await client.get(f"{API}/matters/team/people", headers=h)).json()
    assert {p["email"] for p in people} >= {"lead@team.co", "x@team.co", "y@team.co"}

    m = (await client.post(f"{API}/matters", headers=h, json={
        "title": "Long case", "client_name": "C", "lead_counsel_id": x["id"], "opened_on": "2024-04-01",
        "team": [{"user_id": me["id"], "role": "supervising_partner"}],
    })).json()
    mid = m["id"]
    assert m["lead_counsel_id"] == x["id"] and m["assigned_to"] == x["id"]
    assert {(t["role"], t["is_active"]) for t in m["team"]} == {("lead_counsel", True), ("supervising_partner", True)}
    lead_row = next(t for t in m["team"] if t["role"] == "lead_counsel")
    assert lead_row["from_date"] == "2024-04-01" and lead_row["user_name"] == "Adv. X Mehta"

    # Same person, same role twice → conflict.
    dup = await client.post(f"{API}/matters/{mid}/team", headers=h, json={"user_id": x["id"], "role": "lead_counsel"})
    assert dup.status_code == 409

    # A junior joins with a per-matter rate override.
    jr = await client.post(f"{API}/matters/{mid}/team", headers=h, json={
        "user_id": y["id"], "role": "junior", "rate_basis": "hourly", "rate_amount": 1500,
    })
    assert jr.status_code == 201 and jr.json()["rate_amount"] == "1500.00"

    # Two years in, X leaves the firm: hand the lead role to Y from a date, with the reason.
    ho = await client.post(f"{API}/matters/{mid}/team/{lead_row['id']}/handover", headers=h, json={
        "effective_from": "2026-05-15", "reason": "left_firm", "successor_user_id": y["id"],
    })
    assert ho.status_code == 200, ho.text
    ended, started = ho.json()
    assert ended["to_date"] == "2026-05-15" and ended["end_reason"] == "left_firm"
    assert ended["successor_user_id"] == y["id"] and ended["successor_name"] == "Adv. Y Rao" and ended["is_active"] is False
    assert started["user_id"] == y["id"] and started["role"] == "lead_counsel" and started["from_date"] == "2026-05-15"

    detail = (await client.get(f"{API}/matters/{mid}", headers=h)).json()
    assert detail["lead_counsel_id"] == y["id"] and detail["lead_counsel_name"] == "Adv. Y Rao"
    # History kept: X's row is still there, ended, plus Y's two active roles.
    assert len(detail["team"]) == 4
    assert any(t["user_id"] == x["id"] and t["to_date"] == "2026-05-15" for t in detail["team"])
    # A stint cannot be ended twice.
    again = await client.post(f"{API}/matters/{mid}/team/{lead_row['id']}/handover", headers=h, json={})
    assert again.status_code == 422

    # Bulk: Y now leaves too — every active stint moves to me in one call.
    m2 = (await client.post(f"{API}/matters", headers=h, json={"title": "Second", "client_name": "C2", "lead_counsel_id": y["id"]})).json()
    tr = await client.post(f"{API}/matters/team/transfer", headers=h, json={
        "from_user_id": y["id"], "to_user_id": me["id"], "reason": "left_firm", "effective_from": "2026-06-01",
    })
    assert tr.status_code == 200, tr.text
    assert tr.json()["moved"] == 3 and set(tr.json()["matter_numbers"]) == {m["matter_number"], m2["matter_number"]}
    d1 = (await client.get(f"{API}/matters/{mid}", headers=h)).json()
    d2 = (await client.get(f"{API}/matters/{m2['id']}", headers=h)).json()
    assert d1["lead_counsel_id"] == me["id"] and d2["lead_counsel_id"] == me["id"]
    active1 = {(t["user_id"], t["role"]) for t in d1["team"] if t["is_active"]}
    assert active1 == {(me["id"], "supervising_partner"), (me["id"], "lead_counsel"), (me["id"], "junior")}
    # A stint never ends before it began (the junior row was opened today).
    assert all(t["to_date"] == max("2026-06-01", t["from_date"]) and t["end_reason"] == "left_firm" for t in d1["team"] if t["user_id"] == y["id"])
    # The people put on a matter are told (X was made lead by me at creation).
    notes = (await client.get(f"{API}/notifications", headers=await _login(client, x))).json()
    assert any(n["type"] == "matter_assigned" and n["link"] == f"/app/matters/{mid}" for n in notes)

    # "My matters" — by current team membership.
    mine = await client.get(f"{API}/matters", headers=h, params={"user_id": y["id"]})
    assert mine.json() == []


async def test_fee_arrangement_milestones_and_events(client: AsyncClient, strong_password: str) -> None:
    h, me = await _admin(client, "Fees LLP", "fees@firm.co", strong_password)
    mid = (await client.post(f"{API}/matters", headers=h, json={"title": "Fee case", "client_name": "C"})).json()["id"]

    # Validation: a fixed-fee arrangement needs its fee; percent milestones need a fixed fee.
    bad = await client.post(f"{API}/matters/{mid}/fees", headers=h, json={"basis": "fixed"})
    assert bad.status_code == 422
    bad2 = await client.post(f"{API}/matters/{mid}/fees", headers=h, json={
        "basis": "per_hearing", "per_hearing_fee": 20000,
        "milestones": [{"label": "Advance", "trigger": "advance", "percent": 20}],
    })
    assert bad2.status_code == 422

    # Hybrid: ₹3,00,000 fixed in milestones + ₹25,000 per effective hearing (₹5,000 adjournment).
    arr = await client.post(f"{API}/matters/{mid}/fees", headers=h, json={
        "basis": "hybrid", "fixed_fee": 300000, "per_hearing_fee": 25000, "non_effective_hearing_fee": 5000,
        "agreed_on": "2026-09-01", "effective_from": "2026-09-01", "terms": "Out-of-pocket at actuals.",
        "milestones": [
            {"label": "Advance on engagement", "trigger": "advance", "percent": 30},
            {"label": "On filing", "trigger": "on_filing", "percent": 30},
            {"label": "On first hearing", "trigger": "on_first_hearing", "amount": 60000},
            {"label": "Balance on judgment", "trigger": "on_judgment", "percent": 10, "due_days": 15},
            {"label": "Retention review", "trigger": "on_date", "amount": 1000, "due_on": str(date.today() - timedelta(days=1))},
            {"label": "Ad hoc", "trigger": "manual", "amount": 5000},
        ],
    })
    assert arr.status_code == 201, arr.text
    a = arr.json()
    ms = {m["trigger"]: m for m in a["milestones"]}
    assert ms["advance"]["computed_amount"] == "90000.00" and ms["advance"]["status"] == "due"
    assert ms["on_filing"]["status"] == "pending"

    # The advance fell due on engagement; the dated one on read (its date has passed).
    detail = (await client.get(f"{API}/matters/{mid}", headers=h)).json()
    events = {e["description"]: e for e in detail["fee_events"]}
    assert events["Advance on engagement"]["amount"] == "90000.00" and events["Advance on engagement"]["status"] == "unbilled"
    assert "Retention review" in events and events["Retention review"]["kind"] == "milestone"

    # Stage → filing fires the filing milestone (30% = 90,000, due in 7 days).
    await client.patch(f"{API}/matters/{mid}", headers=h, json={"stage": "filing"})
    detail = (await client.get(f"{API}/matters/{mid}", headers=h)).json()
    filing = next(e for e in detail["fee_events"] if e["description"] == "On filing")
    assert filing["amount"] == "90000.00"
    assert date.fromisoformat(filing["due_on"]) - date.fromisoformat(filing["occurred_on"]) == timedelta(days=7)
    # Moving stage again does not double-fire.
    await client.patch(f"{API}/matters/{mid}", headers=h, json={"stage": "pleadings"})
    await client.patch(f"{API}/matters/{mid}", headers=h, json={"stage": "filing"})
    detail = (await client.get(f"{API}/matters/{mid}", headers=h)).json()
    assert sum(1 for e in detail["fee_events"] if e["description"] == "On filing") == 1

    # Hearings: held → ₹25,000 appearance + the first-hearing milestone; adjourned → ₹5,000.
    h1 = (await client.post(f"{API}/matters/{mid}/hearings", headers=h, json={"scheduled_on": "2026-10-05T10:30:00Z", "purpose": "Admission"})).json()
    h2 = (await client.post(f"{API}/matters/{mid}/hearings", headers=h, json={"scheduled_on": "2026-11-02T10:30:00Z"})).json()
    await client.patch(f"{API}/matters/hearings/{h1['id']}", headers=h, json={"status": "held"})
    await client.patch(f"{API}/matters/hearings/{h2['id']}", headers=h, json={"status": "adjourned"})
    # Re-saving the same status must not raise a second event.
    await client.patch(f"{API}/matters/hearings/{h1['id']}", headers=h, json={"outcome": "Notice issued"})
    detail = (await client.get(f"{API}/matters/{mid}", headers=h)).json()
    kinds = sorted((e["kind"], e["amount"]) for e in detail["fee_events"])
    assert ("hearing", "25000.00") in kinds and ("hearing_non_effective", "5000.00") in kinds
    assert sum(1 for k, _ in kinds if k == "hearing") == 1
    assert next(e for e in detail["fee_events"] if e["description"] == "On first hearing")["amount"] == "60000.00"
    assert "05/10/2026" in next(e for e in detail["fee_events"] if e["kind"] == "hearing")["description"]

    # Manual milestone + manual event; waive one event; summary adds up.
    manual = next(m for m in a["milestones"] if m["trigger"] == "manual")
    trig = await client.post(f"{API}/matters/{mid}/fees/milestones/{manual['id']}/trigger", headers=h)
    assert trig.status_code == 200 and trig.json()["amount"] == "5000.00"
    assert (await client.post(f"{API}/matters/{mid}/fees/milestones/{manual['id']}/trigger", headers=h)).status_code == 422
    ev = (await client.post(f"{API}/matters/{mid}/fees/events", headers=h, json={"description": "Written opinion", "amount": 15000})).json()
    waived = await client.post(f"{API}/matters/{mid}/fees/events/{ev['id']}/status", headers=h, params={"status": "waived"})
    assert waived.json()["status"] == "waived"
    summary = (await client.get(f"{API}/matters/{mid}/fees/summary", headers=h)).json()
    # 90,000 + 1,000 + 90,000 + 25,000 + 60,000 + 5,000 + 5,000 = 276,000 unbilled; 15,000 waived.
    assert summary["unbilled_total"] == "276000.00" and summary["waived_total"] == "15000.00" and summary["unbilled_count"] == 7

    # Closing the matter fires the closure milestone only if there is one; judgment fires the balance.
    await client.patch(f"{API}/matters/{mid}", headers=h, json={"stage": "judgment"})
    detail = (await client.get(f"{API}/matters/{mid}", headers=h)).json()
    assert next(e for e in detail["fee_events"] if e["description"] == "Balance on judgment")["amount"] == "30000.00"

    # Renegotiation: a new arrangement closes the old one the day before; pro bono clears amounts.
    new = await client.post(f"{API}/matters/{mid}/fees", headers=h, json={"basis": "pro_bono", "effective_from": "2026-12-01", "fixed_fee": 1})
    assert new.status_code == 201 and new.json()["fixed_fee"] is None
    detail = (await client.get(f"{API}/matters/{mid}", headers=h)).json()
    old = next(x for x in detail["fee_arrangements"] if x["id"] == a["id"])
    assert old["effective_to"] == "2026-11-30"  # still current until then; the new one takes over on 01/12
    # Retainer raises its first period on creation.
    mid2 = (await client.post(f"{API}/matters", headers=h, json={"title": "Retainer", "client_name": "R"})).json()["id"]
    ret = await client.post(f"{API}/matters/{mid2}/fees", headers=h, json={"basis": "retainer", "retainer_amount": 50000, "retainer_period": "monthly", "retainer_includes": "Up to 4 hearings"})
    assert ret.status_code == 201
    d2 = (await client.get(f"{API}/matters/{mid2}", headers=h)).json()
    assert [ (e["kind"], e["amount"]) for e in d2["fee_events"] ] == [("retainer", "50000.00")]


async def test_counsel_rate_cards(client: AsyncClient, strong_password: str) -> None:
    h, me = await _admin(client, "Rates LLP", "rates@firm.co", strong_password)
    x = await _colleague(client, h, "Adv. X", "x@rates.co", strong_password)

    r1 = await client.post(f"{API}/rates", headers=h, json={"user_id": x["id"], "basis": "hourly", "amount": 4000, "effective_from": "2026-01-01"})
    assert r1.status_code == 201, r1.text
    r2 = await client.post(f"{API}/rates", headers=h, json={"user_id": x["id"], "basis": "per_hearing", "amount": 20000})
    assert r2.status_code == 201
    # A later hourly rate supersedes the open one (ends it the day before).
    r3 = await client.post(f"{API}/rates", headers=h, json={"user_id": x["id"], "basis": "hourly", "amount": 5000, "effective_from": "2026-07-01"})
    assert r3.status_code == 201
    cards = (await client.get(f"{API}/rates/cards", headers=h)).json()
    card = next(c for c in cards if c["user_id"] == x["id"])
    hourly = sorted((r for r in card["rates"] if r["basis"] == "hourly"), key=lambda r: r["effective_from"])
    assert hourly[0]["effective_to"] == "2026-06-30" and hourly[0]["is_current"] is False
    assert hourly[1]["amount"] == "5000.00" and hourly[1]["is_current"] is True
    # Another open rate starting earlier than an existing open one is refused.
    clash = await client.post(f"{API}/rates", headers=h, json={"user_id": x["id"], "basis": "hourly", "amount": 1, "effective_from": "2026-03-01"})
    assert clash.status_code == 422
    # Someone from another tenant cannot be given a rate here.
    other_h, other = await _admin(client, "Other LLP", "o@other.co", strong_password)
    assert (await client.post(f"{API}/rates", headers=h, json={"user_id": other["id"], "basis": "hourly", "amount": 1})).status_code == 404
    assert all(c["user_id"] != x["id"] for c in (await client.get(f"{API}/rates/cards", headers=other_h)).json())

    # The card shows on the team row (per-matter override wins for display of rate_amount).
    created_resp = await client.post(f"{API}/matters", headers=h, json={"title": "Rate case", "client_name": "C", "lead_counsel_id": x["id"]})
    assert created_resp.status_code == 201, created_resp.text
    mid = created_resp.json()["id"]
    detail = (await client.get(f"{API}/matters/{mid}", headers=h)).json()
    row = detail["team"][0]
    assert row["card_rate_basis"] == "hourly" and row["card_rate_amount"] == "5000.00" and row["rate_amount"] is None
    upd = await client.patch(f"{API}/matters/{mid}/team/{row['id']}", headers=h, json={"rate_basis": "per_hearing", "rate_amount": 30000})
    assert upd.json()["rate_amount"] == "30000.00" and upd.json()["card_rate_basis"] == "per_hearing" and upd.json()["card_rate_amount"] == "20000.00"

    # Delete.
    assert (await client.delete(f"{API}/rates/{r2.json()['id']}", headers=h)).status_code == 204


async def test_team_workload(client: AsyncClient, strong_password: str) -> None:
    from datetime import UTC, datetime
    h, me = await _admin(client, "Load LLP", "load@firm.co", strong_password)
    x = await _colleague(client, h, "Adv. Busy", "busy@firm.co", strong_password)
    await _colleague(client, h, "Adv. Free", "free@firm.co", strong_password)
    soon = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    later = (datetime.now(UTC) + timedelta(days=40)).isoformat()
    ids = []
    for title in ("A v. B", "C v. D", "E v. F"):
        m = (await client.post(f"{API}/matters", headers=h, json={
            "title": title, "client_name": "Client", "lead_counsel_id": x["id"]})).json()
        ids.append(m["id"])
    await client.post(f"{API}/matters/{ids[0]}/team", headers=h, json={"user_id": me["id"], "role": "associate"})
    await client.post(f"{API}/matters/{ids[0]}/hearings", headers=h, json={"scheduled_on": soon})
    await client.post(f"{API}/matters/{ids[1]}/hearings", headers=h, json={"scheduled_on": later})
    # A closed matter no longer counts.
    await client.patch(f"{API}/matters/{ids[2]}", headers=h, json={"status": "closed"})

    resp = await client.get(f"{API}/matters/team/workload", headers=h)
    assert resp.status_code == 200, resp.text
    rows = {r["full_name"]: r for r in resp.json()}
    assert resp.json()[0]["full_name"] == "Adv. Busy"
    busy = rows["Adv. Busy"]
    assert (busy["open_matters"], busy["lead_matters"], busy["roles"], busy["hearings_next_14_days"]) == (2, 2, {"lead_counsel": 2}, 1)
    mine = rows[me["full_name"]]
    assert (mine["open_matters"], mine["roles"], mine["hearings_next_14_days"]) == (1, {"associate": 1}, 1)
    assert rows["Adv. Free"]["open_matters"] == 0

    # Another organisation sees only its own people.
    h2, _ = await _admin(client, "Other LLP", "other@firm.co", strong_password)
    assert [r["full_name"] for r in (await client.get(f"{API}/matters/team/workload", headers=h2)).json()] == ["Adv. Other"]


async def test_team_conflict_check(client: AsyncClient, strong_password: str) -> None:
    h, me = await _admin(client, "Conflict LLP", "conf@firm.co", strong_password)
    x = await _colleague(client, h, "Adv. Past", "past@firm.co", strong_password)
    clean = await _colleague(client, h, "Adv. Clean", "clean@firm.co", strong_password)

    async def matter(title: str, client_name: str, opposing: list[str], lead: str) -> str:
        m = (await client.post(f"{API}/matters", headers=h, json={
            "title": title, "client_name": client_name, "lead_counsel_id": lead})).json()
        for name in opposing:
            r = await client.post(f"{API}/matters/{m['id']}/parties", headers=h,
                                  json={"name": name, "role": "respondent", "side": "opposing"})
            assert r.status_code == 201, r.text
        return m["id"]

    # Earlier, X acted against Sharma Traders, and for Gupta Builders.
    old1 = await matter("Kumar v. Sharma Traders", "Ravi Kumar", ["Sharma Traders Pvt. Ltd."], x["id"])
    await matter("Gupta Builders v. State", "M/s Gupta Builders", ["State of Delhi"], x["id"])
    # X's stint on the first one has since ended (handed to me).
    team = (await client.get(f"{API}/matters/{old1}", headers=h)).json()["team"]
    ended = await client.post(f"{API}/matters/{old1}/team/{team[0]['id']}/handover", headers=h,
                              json={"successor_user_id": me["id"], "reason": "reassigned"})
    assert ended.status_code in (200, 201), ended.text

    # Now: we act for Sharma Traders against Gupta Builders.
    new = await matter("Sharma Traders v. Gupta Builders", "M/s Sharma Traders", ["Gupta Builders Ltd"], me["id"])
    resp = await client.get(f"{API}/matters/{new}/team/conflicts", headers=h, params={"user_id": x["id"]})
    assert resp.status_code == 200, resp.text
    hits = {(c["kind"], c["party_name"], c["current"]) for c in resp.json()}
    assert hits == {("acted_for_opponent", "Gupta Builders Ltd", True),
                    ("acted_against_client", "M/s Sharma Traders", False)}

    assert (await client.get(f"{API}/matters/{new}/team/conflicts", headers=h,
                             params={"user_id": clean["id"]})).json() == []
    # Another firm cannot probe this matter.
    h2, _ = await _admin(client, "Else LLP", "else@firm.co", strong_password)
    assert (await client.get(f"{API}/matters/{new}/team/conflicts", headers=h2,
                             params={"user_id": x["id"]})).status_code == 404


def test_retainer_period_starts() -> None:
    from types import SimpleNamespace
    from app.modules.matters.fee_sweep import add_months, period_starts
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28) and add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    arr = SimpleNamespace(retainer_period="quarterly", effective_from=date(2026, 1, 31), effective_to=None)
    assert period_starts(arr, date(2026, 10, 22)) == [date(2026, 1, 31), date(2026, 4, 30), date(2026, 7, 31)]
    arr.effective_to = date(2026, 5, 1)
    assert period_starts(arr, date(2026, 10, 22)) == [date(2026, 1, 31), date(2026, 4, 30)]


async def test_fee_sweep_raises_retainer_periods_and_dated_milestones(
    client: AsyncClient, strong_password: str, session_factory
) -> None:
    from app.modules.matters.fee_sweep import sweep
    h, _ = await _admin(client, "Sweep LLP", "sweep@firm.co", strong_password)
    today = date.today()
    start = today - timedelta(days=75)  # three monthly periods so far (or so)
    mid = (await client.post(f"{API}/matters", headers=h, json={"title": "Retained", "client_name": "R"})).json()["id"]
    assert (await client.post(f"{API}/matters/{mid}/fees", headers=h, json={
        "basis": "retainer", "retainer_amount": 20000, "retainer_period": "monthly", "effective_from": start.isoformat(),
    })).status_code == 201
    m2 = (await client.post(f"{API}/matters", headers=h, json={"title": "Staged", "client_name": "S"})).json()["id"]
    assert (await client.post(f"{API}/matters/{m2}/fees", headers=h, json={
        "basis": "milestone", "fixed_fee": 100000, "milestones": [
            {"label": "Second instalment", "trigger": "on_date", "due_on": (today - timedelta(days=1)).isoformat(), "percent": 40},
            {"label": "Final instalment", "trigger": "on_date", "due_on": (today + timedelta(days=30)).isoformat(), "percent": 60},
        ]})).status_code == 201
    # A closed matter's retainer stops.
    m3 = (await client.post(f"{API}/matters", headers=h, json={"title": "Closed", "client_name": "C"})).json()["id"]
    await client.post(f"{API}/matters/{m3}/fees", headers=h, json={
        "basis": "retainer", "retainer_amount": 5000, "retainer_period": "monthly", "effective_from": start.isoformat()})
    await client.patch(f"{API}/matters/{m3}", headers=h, json={"status": "closed"})

    from app.modules.matters.fee_sweep import period_starts
    from types import SimpleNamespace
    expected = len(period_starts(SimpleNamespace(retainer_period="monthly", effective_from=start, effective_to=None), today))
    async with session_factory() as s:
        first = await sweep(s, today)
        await s.commit()
    assert first == {"retainer_periods": expected - 1, "dated_milestones": 1, "recurring_invoices": 0}
    async with session_factory() as s:
        assert await sweep(s, today) == {"retainer_periods": 0, "dated_milestones": 0, "recurring_invoices": 0}  # idempotent
        await s.commit()

    events = (await client.get(f"{API}/matters/{mid}", headers=h)).json()["fee_events"]
    assert sorted(e["occurred_on"] for e in events) == [d.isoformat() for d in period_starts(
        SimpleNamespace(retainer_period="monthly", effective_from=start, effective_to=None), today)]
    staged = (await client.get(f"{API}/matters/{m2}", headers=h)).json()
    assert [(e["description"], e["amount"]) for e in staged["fee_events"]] == [("Second instalment", "40000.00")]
    assert len((await client.get(f"{API}/matters/{m3}", headers=h)).json()["fee_events"]) == 1  # only the first period


async def test_expenses_are_billed_at_cost(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _admin(client, "Expense LLP", "expense@firm.co", strong_password)
    mid = (await client.post(f"{API}/matters", headers=h, json={"title": "Costs", "client_name": "C"})).json()["id"]
    ev = await client.post(f"{API}/matters/{mid}/fees/events", headers=h,
                           json={"kind": "expense", "description": "Court fee on the plaint", "amount": 1250})
    assert ev.status_code == 201, ev.text
    assert ev.json()["kind"] == "expense"
    fee = await client.post(f"{API}/matters/{mid}/fees/events", headers=h, json={"description": "Drafting the plaint", "amount": 20000})
    assert fee.json()["kind"] == "manual"          # the default
    # Only manual fees and expenses are raised by hand.
    assert (await client.post(f"{API}/matters/{mid}/fees/events", headers=h,
                              json={"kind": "retainer", "description": "x", "amount": 1})).status_code == 422
    inv = await client.post(f"{API}/billing/matters/{mid}/prepare-invoice", headers=h, json={})
    assert inv.status_code == 201, inv.text
    assert sorted(li["description"] for li in inv.json()["line_items"]) == ["Drafting the plaint", "Expense: Court fee on the plaint"]
