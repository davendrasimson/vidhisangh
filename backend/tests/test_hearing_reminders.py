"""Evening WhatsApp reminders of tomorrow's hearings, and adding a verified mobile number."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.whatsapp import WhatsAppError
from app.modules.notifications import hearing_reminders as reminders
from app.modules.notifications.models import HearingReminderSend

pytestmark = pytest.mark.asyncio

API = "/api/v1"


@pytest.fixture
def codes(monkeypatch):
    sent: list[tuple[str, str]] = []

    async def send(phone, code):
        sent.append((phone, code))

    monkeypatch.setattr("app.modules.identity.phone_otp.send_whatsapp_code", send)
    return sent


class Recorder:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str, str, list[str]]] = []
        self.fail = fail

    async def send_template(self, phone, template, lang, body):
        if self.fail:
            raise WhatsAppError("HTTP 400 code 132001")
        self.sent.append((phone, template, lang, body))
        return "wamid.test"


async def _user(client: AsyncClient, org: str, email: str, pw: str) -> tuple[dict, dict]:
    resp = await client.post(f"{API}/auth/register", json={
        "organisation_name": org, "full_name": f"Adv. {email.split('@')[0].title()}",
        "email": email, "password": pw, "accept_terms": True,
    })
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    return headers, (await client.get(f"{API}/auth/me", headers=headers)).json()


async def _verify_phone(client: AsyncClient, headers: dict, phone: str, codes: list) -> dict:
    resp = await client.post(f"{API}/auth/me/phone/request", headers=headers, json={"phone": phone})
    assert resp.status_code == 200, resp.text
    challenge = resp.json()["challenge_id"]
    resp = await client.post(f"{API}/auth/me/phone/verify", headers=headers,
                             json={"challenge_id": challenge, "code": codes[-1][1]})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _at(day, hour: int, minute: int = 0) -> str:
    """India time, sent in UTC like the app does."""
    utc = datetime.combine(day, time(hour, minute), reminders.IST).astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


async def test_adding_a_mobile_number_with_a_whatsapp_code(client: AsyncClient, strong_password: str, codes) -> None:
    h, me = await _user(client, "Rao Chambers", "rao@example.com", strong_password)
    assert not me.get("is_phone_verified")
    me = await _verify_phone(client, h, "98765 43210", codes)
    assert me["phone"] == "+919876543210" and me["is_phone_verified"] is True
    assert codes[-1][0] == "+919876543210"

    again = await client.post(f"{API}/auth/me/phone/request", headers=h, json={"phone": "+919876543210"})
    assert again.status_code == 409 and "already verified on your account" in again.text

    # Another member cannot take a number already proven by someone else.
    h2, _ = await _user(client, "Other Firm", "other@example.com", strong_password)
    taken = await client.post(f"{API}/auth/me/phone/request", headers=h2, json={"phone": "+919876543210"})
    assert taken.status_code == 409 and "another VidhiSangh account" in taken.text

    # A code sent to one member cannot be used by another.
    resp = await client.post(f"{API}/auth/me/phone/request", headers=h2, json={"phone": "+919812345678"})
    challenge = resp.json()["challenge_id"]
    stolen = await client.post(f"{API}/auth/me/phone/verify", headers=h,
                               json={"challenge_id": challenge, "code": codes[-1][1]})
    assert stolen.status_code == 401
    wrong = await client.post(f"{API}/auth/me/phone/verify", headers=h2,
                              json={"challenge_id": challenge, "code": "000000" if codes[-1][1] != "000000" else "111111"})
    assert wrong.status_code == 401


async def test_one_evening_message_lists_tomorrows_hearings(
    client: AsyncClient, strong_password: str, codes, session_factory,
) -> None:
    day = reminders.tomorrow_ist()
    h, me = await _user(client, "Rao Chambers", "rao@example.com", strong_password)
    await _verify_phone(client, h, "+919876543210", codes)
    pref = await client.put(f"{API}/notifications/preferences/whatsapp", headers=h, json={"enabled": True, "types": []})
    assert pref.status_code == 200, pref.text

    mid = (await client.post(f"{API}/matters", headers=h, json={
        "title": "Sharma v. State", "client_name": "Sharma", "case_number": "CRL.A. 12/2026", "court": "Delhi High Court",
    })).json()["id"]
    other = (await client.post(f"{API}/matters", headers=h, json={"title": "Gupta v. Gupta", "client_name": "Gupta"})).json()["id"]
    for matter, when, purpose in ((mid, _at(day, 10, 30), "Arguments"), (other, _at(day, 0), None),
                                  (mid, _at(day + timedelta(days=1), 10, 30), "Not tomorrow")):
        resp = await client.post(f"{API}/matters/{matter}/hearings", headers=h,
                                 json={"scheduled_on": when, **({"purpose": purpose} if purpose else {})})
        assert resp.status_code == 201, resp.text

    # Another firm's member with a hearing tomorrow who has not opted in gets nothing.
    h2, _ = await _user(client, "Other Firm", "other@example.com", strong_password)
    m2 = (await client.post(f"{API}/matters", headers=h2, json={"title": "X v. Y", "client_name": "X"})).json()["id"]
    await client.post(f"{API}/matters/{m2}/hearings", headers=h2, json={"scheduled_on": _at(day, 11)})

    recorder = Recorder()
    async with session_factory() as session:
        due = await reminders.collect(session, day)
        assert [str(r.user_id) for r in due] == [me["id"]]
        report = await reminders.send_reminders(session, recorder, day, due)
    assert report == {"sent": 1, "already": 0, "failed": 0}
    phone, template, lang, body = recorder.sent[0]
    assert (phone, template, lang) == ("+919876543210", "hearing_reminder", "en")
    assert body[0] == "Adv. Rao"
    assert body[1] == f"{day.strftime('%a')} {day.strftime('%d/%m/%Y')}"
    assert body[2].startswith("1. Gupta v. Gupta")  # no time given: listed first, without a time
    assert "2. Sharma v. State (CRL.A. 12/2026), Delhi High Court, 10:30 am, for Arguments" in body[2]
    assert "Not tomorrow" not in body[2] and "\n" not in body[2]

    # A rerun the same evening sends nothing more.
    async with session_factory() as session:
        again = await reminders.send_reminders(session, recorder, day, await reminders.collect(session, day))
    assert again == {"sent": 0, "already": 1, "failed": 0} and len(recorder.sent) == 1

    # Turned off: nothing is collected.
    await client.put(f"{API}/notifications/preferences/whatsapp", headers=h, json={"enabled": False, "types": []})
    async with session_factory() as session:
        assert await reminders.collect(session, day + timedelta(days=1)) == []


async def test_a_refused_message_is_recorded_and_not_retried(
    client: AsyncClient, strong_password: str, codes, session_factory,
) -> None:
    day = reminders.tomorrow_ist()
    h, _ = await _user(client, "Rao Chambers", "rao@example.com", strong_password)
    await _verify_phone(client, h, "+919876543210", codes)
    await client.put(f"{API}/notifications/preferences/whatsapp", headers=h, json={"enabled": True, "types": []})
    mid = (await client.post(f"{API}/matters", headers=h, json={"title": "A v. B", "client_name": "A"})).json()["id"]
    await client.post(f"{API}/matters/{mid}/hearings", headers=h, json={"scheduled_on": _at(day, 11)})

    async with session_factory() as session:
        report = await reminders.send_reminders(session, Recorder(fail=True), day, await reminders.collect(session, day))
        assert report["failed"] == 1
        row = await session.scalar(select(HearingReminderSend))
        assert row.status == "failed" and row.hearing_count == 1 and "132001" in row.detail
        assert (await reminders.send_reminders(session, Recorder(), day, await reminders.collect(session, day)))["already"] == 1


def test_a_long_board_is_cut_with_a_count() -> None:
    items = [f"{i}. Matter number {i} v. State (W.P.(C) {i}/2026), Delhi High Court, 10:30 am" for i in range(1, 31)]
    text = reminders.hearing_list(items)
    assert len(text) <= reminders.LIST_LIMIT
    shown = text.count("v. State")
    assert text.endswith(f"; and {30 - shown} more") and shown >= 5
    assert reminders.hearing_list(items[:2]) == "; ".join(items[:2])
