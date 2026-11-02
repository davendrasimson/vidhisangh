"""The Supreme Court digest on WhatsApp follows the email digest, to consenting members, once a day."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.whatsapp import WhatsAppError, set_whatsapp_sender
from app.modules.identity.models import User
from app.modules.notifications.models import WhatsAppCampaignSend
from app.modules.notifications.whatsapp_updates import record_choice
from app.modules.profile.models import ProfessionalProfile
from app.modules.research import daily_orders as daily
from app.modules.research import daily_whatsapp as wa
from app.modules.research.ai_headnotes import apply_ai_headnote
from app.modules.research.daily_source import OrderEntry, official_url
from app.modules.research.models import Judgment
from tests.test_daily_sc_orders import HEADNOTE, URL, MailRecorder, verified_user
from tests.test_matters import API, _user

pytestmark = pytest.mark.asyncio


class WaRecorder:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.sent: list[tuple[str, str, str, list[str]]] = []
        self.fail = fail or set()

    async def send_template(self, phone: str, template: str, lang: str, body: list[str]) -> str:
        if phone in self.fail:
            raise WhatsAppError("HTTP 400 code 131026")
        self.sent.append((phone, template, lang, body))
        return "wamid.test"


@pytest.fixture(autouse=True)
def _no_real_whatsapp():
    yield
    set_whatsapp_sender(None, active=False)


async def _ready_orders(session_factory, count: int, first_seen: datetime) -> None:
    async with session_factory() as session:
        entries = [OrderEntry(f"State of UP v. Ramesh Chandra {i}\n(bail)", first_seen.date(), official_url(URL + str(i)))
                   for i in range(count)]
        await daily.register_entries(session, entries, first_seen)
        for judgment in await session.scalars(select(Judgment)):
            await apply_ai_headnote(session, judgment.id, HEADNOTE, model="offline-reviewed")
        await session.commit()


def test_parameters_are_single_line_and_short():
    assert wa.clean("A very\nlong  case\tname " + "x" * 200, 120).endswith("…")
    assert len(wa.clean("x" * 500, 120)) == 120
    assert wa.date_text(date(2026, 11, 2), "en") == "2 November 2026"
    assert wa.date_text(date(2026, 11, 2), "hi") == "2 नवंबर 2026"
    assert wa.campaign_name(date(2026, 11, 2)) == "sc-daily-2026-11-02"


async def test_whatsapp_digest_follows_the_email_digest_for_consenting_members(client, session_factory, strong_password):
    # Three subscribers: Daily (verified number, said yes), Quiet (number, said no), Mail (no number).
    h1, daily_id = await verified_user(client, session_factory, strong_password)
    h2, quiet = await _user(client, "Quiet LLP", "quiet@firm.co", strong_password)
    h3, mail_only = await _user(client, "Mail LLP", "mail@firm.co", strong_password)
    quiet_id, mail_id = uuid.UUID(quiet["id"]), uuid.UUID(mail_only["id"])
    async with session_factory() as s:
        for uid, phone, yes in ((daily_id, "+919876543210", True), (quiet_id, "+919876543211", False), (mail_id, None, True)):
            user = await s.get(User, uid)
            user.is_email_verified = True
            if phone:
                user.phone, user.is_phone_verified = phone, True
            await record_choice(s, uid, yes, source="test", ip=None)
        profile = await s.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == daily_id))
        if profile is None:
            s.add(ProfessionalProfile(tenant_id=(await s.get(User, daily_id)).tenant_id, user_id=daily_id, languages=["Hindi"]))
        else:
            profile.languages = ["Hindi"]
        await s.commit()
    for h in (h1, h2, h3):
        assert (await client.put(f"{API}/notifications/daily-orders", headers=h, json={"enabled": True})).status_code == 200

    first_seen = datetime.now(UTC) + timedelta(seconds=1)
    await _ready_orders(session_factory, 3, first_seen)
    day = first_seen.date()
    recorder = WaRecorder()
    async with session_factory() as s:
        # Before the email digest: nothing on WhatsApp (it describes the same orders the email carried).
        assert (await wa.send_whatsapp_digests(s, recorder, day))["sent"] == 0 and not recorder.sent
        assert (await daily.send_digests(s, MailRecorder(), day))["sent"] == 3
        report = await wa.send_whatsapp_digests(s, recorder, day, dry_run=True)
        assert report["eligible"] == 1 and report["no_consent"] == 1 and report["no_number"] == 1 and not recorder.sent
        report = await wa.send_whatsapp_digests(s, recorder, day)
        assert report["sent"] == 1 and report["failed"] == 0
        # Rerun: claimed already, never twice.
        assert (await wa.send_whatsapp_digests(s, recorder, day))["already"] == 1
    assert len(recorder.sent) == 1
    phone, template, lang, body = recorder.sent[0]
    assert phone == "+919876543210" and template == "sc_daily_orders" and lang == "hi"  # Hindi-only profile
    assert body[:3] == ["Daily", "3", f"{day.day} {wa.HINDI_MONTHS[day.month - 1]} {day.year}"]
    # The leading case is the first order of the email digest, with the line break in its name folded.
    assert body[3].startswith("State of UP v. Ramesh Chandra ") and body[3].endswith(" (bail)") and body[4] == "Appeal allowed."
    assert all("\n" not in value and "\t" not in value for value in body)
    async with session_factory() as s:
        rows = list(await s.scalars(select(WhatsAppCampaignSend).where(WhatsAppCampaignSend.campaign == f"sc-daily-{day.isoformat()}")))
        assert len(rows) == 1 and rows[0].status == "sent" and rows[0].basis == "consent" and rows[0].user_id == daily_id
        assert "9876543210" not in rows[0].phone_hash


async def test_whatsapp_failure_is_recorded_and_not_retried_that_day(client, session_factory, strong_password):
    h, uid = await verified_user(client, session_factory, strong_password)
    async with session_factory() as s:
        user = await s.get(User, uid)
        user.phone, user.is_phone_verified = "+919000000001", True
        await record_choice(s, uid, True, source="test", ip=None)
        await s.commit()
    assert (await client.put(f"{API}/notifications/daily-orders", headers=h, json={"enabled": True})).status_code == 200
    first_seen = datetime.now(UTC) + timedelta(seconds=1)
    await _ready_orders(session_factory, 1, first_seen)
    recorder = WaRecorder(fail={"+919000000001"})
    async with session_factory() as s:
        await daily.send_digests(s, MailRecorder(), first_seen.date())
        assert (await wa.send_whatsapp_digests(s, recorder, first_seen.date()))["failed"] == 1
        assert (await wa.send_whatsapp_digests(s, recorder, first_seen.date()))["already"] == 1
        row = await s.scalar(select(WhatsAppCampaignSend))
        assert row.status == "failed" and "131026" in row.detail
