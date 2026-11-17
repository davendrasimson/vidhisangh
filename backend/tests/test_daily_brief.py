"""VidhiSangh Daily: the page, the quiz, the landmark picker and the morning push."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.push import PushMessage
from app.core.whatsapp import WhatsAppError
from app.modules.brief import service
from app.modules.brief.models import DailyBriefEmail, DailyBriefEmailPreference, DailyBriefSend, DailyQuizAnswer
from app.modules.identity.models import User
from app.modules.network import official
from app.modules.notifications.models import WhatsAppCampaignSend
from app.modules.notifications.whatsapp_updates import record_choice
from app.modules.profile.models import ProfessionalProfile
from app.modules.research.models import CourtLevel, Judgment
from tests.test_official_posts import HEADNOTE, NOW, _member, _seed

pytestmark = pytest.mark.asyncio
API = "/api/v1"
WEDNESDAY = date(2026, 11, 4)
SATURDAY = date(2026, 11, 7)
SUNDAY = date(2026, 11, 8)


class PushRecorder:
    def __init__(self) -> None:
        self.sent: list[tuple[str, PushMessage]] = []

    async def send(self, device_token, message):  # noqa: ANN001
        self.sent.append((device_token, message))
        return "sent"


def test_the_lead_rotates_by_weekday_and_the_quiz_walks_the_bank() -> None:
    assert [service.lead_for(date(2026, 11, d)) for d in range(2, 9)] == [
        "section", "judgment", "quiz", "on_this_day", "news", "fraternity", "on_this_day"]
    assert service.pushes_on(SATURDAY) and not service.pushes_on(SUNDAY)
    bank = service.quiz_bank()
    assert len(bank) >= 90 and len({q["id"] for q in bank}) == len(bank)
    for q in bank:
        assert len(q["options"]) == 4 and 0 <= q["answer"] < 4 and q["explanation"]
    first = [service.quiz_for(date.fromordinal(service.EPOCH.toordinal() + i))["id"] for i in range(len(bank))]
    assert len(set(first)) == len(bank), "every question comes up once before any repeats"
    assert service.quiz_for(date.fromordinal(service.EPOCH.toordinal() + len(bank))) == service.quiz_for(service.EPOCH)


def test_curated_landmarks_are_well_formed_and_cover_the_famous_dates() -> None:
    entries = service.landmarks()
    assert len(entries) >= 100
    for e in entries:
        date.fromisoformat(e["date"])
        assert e["case"] and e["holding"] and e["match"]
    assert service.landmark_for(date(2027, 4, 24))["case"].startswith("Kesavananda")
    assert service.landmark_for(date(2027, 8, 24))["case"].startswith("K.S. Puttaswamy")
    # Three landmarks share 26 September; the year picks one so they rotate.
    picks = {service.landmark_for(date(y, 9, 26))["case"] for y in (2027, 2028, 2029)}
    assert len(picks) == 3


async def test_the_page_shows_the_day_and_the_quiz_reveals_only_after_answering(
    client: AsyncClient, strong_password: str, session_factory,
) -> None:
    h = await _member(client, strong_password)
    await _seed(session_factory)
    async with session_factory() as s:
        await official.post_daily(s, NOW)
        await s.commit()

    r = await client.get(f"{API}/brief", headers=h, params={"day": WEDNESDAY.isoformat(), "from": "push"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["lead"] == "quiz" and b["weekday"] == "Wednesday"
    assert b["section"]["kind"] == "section" and b["judgment"]["kind"] == "judgment" and len(b["news"]) == 1
    q = b["quiz"]
    assert q["answer"] is None and q["explanation"] is None and q["chosen"] is None and len(q["options"]) == 4
    assert q["stats"] == {"answers": 0, "right": 0}
    assert b["fraternity"]["members"] >= 1 and isinstance(b["fraternity"]["people"], list)

    expected = service.quiz_by_id(q["id"])
    wrong = (expected["answer"] + 1) % 4
    r = await client.post(f"{API}/brief/quiz/{q['id']}/answer", headers=h, json={"chosen": wrong})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["correct"] is False and a["answer"] == expected["answer"] and a["explanation"] == expected["explanation"]
    assert a["stats"] == {"answers": 1, "right": 0}
    # A second attempt does not change the recorded answer.
    r = await client.post(f"{API}/brief/quiz/{q['id']}/answer", headers=h, json={"chosen": expected["answer"]})
    assert r.json()["chosen"] == wrong and r.json()["stats"] == {"answers": 1, "right": 0}
    assert (await client.post(f"{API}/brief/quiz/nope/answer", headers=h, json={"chosen": 0})).status_code == 404

    b = (await client.get(f"{API}/brief", headers=h, params={"day": WEDNESDAY.isoformat()})).json()
    assert b["quiz"]["chosen"] == wrong and b["quiz"]["answer"] == expected["answer"]
    assert (await client.get(f"{API}/brief", headers=h, params={"day": "2999-01-01"})).status_code == 404

    async with session_factory() as s:
        answers = (await s.scalars(select(DailyQuizAnswer))).all()
        assert len(answers) == 1 and answers[0].quiz_id == q["id"] and answers[0].correct is False
        # Opening today's page from the push is recorded (only for today, so the Wednesday fixture adds nothing).
        views = (await s.scalars(select(DailyBriefSend))).all()
        assert all(v.for_date == service.today_ist() for v in views)


async def test_on_this_day_prefers_the_curated_landmark_and_falls_back_to_the_most_cited(session_factory) -> None:
    actor = uuid.UUID(int=0)
    async with session_factory() as s:
        # 24 April: Kesavananda is curated; the corpus copy carries the registry's spelling and is linked.
        k = Judgment(case_name="HIS HOLINESS KESAVANANDA BHARATI SRIPADAGALAVARU versus STATE OF KERALA", court="Supreme Court",
                     court_level=CourtLevel.SUPREME_COURT, judgment_date=date(1973, 4, 24), added_by=actor)
        # 3 June in two earlier years: the one later judgments cite more (mined alias support) wins the fallback;
        # Gamma is cited too rarely to count; Beta has no AI headnote, so the card says only what is certain.
        a = Judgment(case_name="ALPHA versus STATE R1: STATE R2: SOMEONE", court="Supreme Court", court_level=CourtLevel.SUPREME_COURT,
                     judgment_date=date(1990, 6, 3), ai_headnote={**HEADNOTE, "summary": "Alpha holding."}, added_by=actor)
        b = Judgment(case_name="BETA versus STATE", court="Supreme Court", court_level=CourtLevel.SUPREME_COURT,
                     judgment_date=date(2001, 6, 3), headnote="In the result, the appeal is allowed.", added_by=actor)
        plain = Judgment(case_name="GAMMA versus STATE", court="Supreme Court", court_level=CourtLevel.SUPREME_COURT,
                         judgment_date=date(2005, 6, 3), added_by=actor)
        s.add_all([k, a, b, plain])
        await s.flush()
        from app.modules.research.models import JudgmentAlias
        s.add(JudgmentAlias(judgment_id=a.id, citation="(1990) 2 SCC 1", reporter="SCC", support=5))
        s.add(JudgmentAlias(judgment_id=b.id, citation="(2001) 4 SCC 9", reporter="SCC", support=3))
        s.add(JudgmentAlias(judgment_id=plain.id, citation="(2005) 1 SCC 7", reporter="SCC", support=2))
        await s.commit()
        kid, aid = k.id, a.id

    async with session_factory() as s:
        curated = await service.on_this_day(s, date(2027, 4, 24))
        assert curated["source"] == "curated" and curated["judgment_id"] == kid and curated["decided"] == date(1973, 4, 24)
        corpus = await service.on_this_day(s, date(2027, 6, 3))
        assert corpus["source"] == "corpus" and corpus["judgment_id"] == aid and corpus["holding"] == "Alpha holding."
        assert corpus["case"] == "Alpha v. State" and corpus["basis"] == "ai" and corpus["cited"] == 5
        # With Alpha gone, Beta is next; the registry's text fragment is never shown as a holding.
        await s.delete(await s.get(Judgment, aid))
        await s.flush()
        beta = await service.on_this_day(s, date(2027, 6, 3))
        assert beta["case"] == "Beta v. State" and beta["basis"] == "cited" and beta["cited"] == 3
        assert "3 citations" in beta["holding"] and "In the result" not in beta["holding"]
        # Gamma alone (2 citations) is below the bar: no card rather than a weak one.
        await s.delete(await s.get(Judgment, beta["judgment_id"]))
        await s.flush()
        assert await service.on_this_day(s, date(2027, 6, 3)) is None
        assert await service.on_this_day(s, date(2027, 2, 2)) is None


async def test_the_morning_push_goes_once_per_member_and_not_on_sunday(
    client: AsyncClient, strong_password: str, session_factory,
) -> None:
    h = await _member(client, strong_password)
    await client.post(f"{API}/notifications/devices", headers=h, json={"token": "fcm-" + "b" * 40, "platform": "android"})
    await _seed(session_factory)
    push = PushRecorder()
    async with session_factory() as s:
        assert await service.send_briefs(s, push, SUNDAY) == {"sent": 0, "already": 0, "failed": 0, "skipped": 0}
        assert await service.send_briefs(s, push, WEDNESDAY) == {"sent": 1, "already": 0, "failed": 0, "skipped": 0}
        assert await service.send_briefs(s, push, WEDNESDAY) == {"sent": 0, "already": 1, "failed": 0, "skipped": 0}
        (token, message), = push.sent
        assert token.startswith("fcm-") and message.title == "Today's question"
        assert message.body.startswith(service.quiz_for(WEDNESDAY)["question"][:40])
        assert message.link == "/app/daily?from=push&lead=quiz"
        row = await s.scalar(select(DailyBriefSend).where(DailyBriefSend.for_date == WEDNESDAY))
        assert row.status == "sent" and row.lead == "quiz" and row.detail == "push x1" and row.opened_at is None
        # The official items were posted by the job itself, so the section exists before anyone is told.
        assert (await official.daily_cards(s))["section"] is not None

        # Saturday's message counts the fraternity; Tuesday's names the judgment.
        assert await service.send_briefs(s, push, SATURDAY) == {"sent": 1, "already": 0, "failed": 0, "skipped": 0}
        assert push.sent[-1][1].title == "Your fraternity" and "joined this week" in push.sent[-1][1].body
        assert await service.send_briefs(s, push, date(2026, 11, 3)) == {"sent": 1, "already": 0, "failed": 0, "skipped": 0}
        assert push.sent[-1][1].title.startswith("Supreme Court") and "Newest v. State" in push.sent[-1][1].body

    # Opening the page marks today's row; the push row stays the record of the send.
    today = service.today_ist()
    async with session_factory() as s:
        await service.mark_opened(s, uuid.UUID((await client.get(f"{API}/auth/me", headers=h)).json()["id"]), today, "push")
        await s.commit()
        row = await s.scalar(select(DailyBriefSend).where(DailyBriefSend.for_date == today))
        assert row is not None and row.opened_via == "push" and row.opened_at is not None
        assert row.opened_at.replace(tzinfo=UTC) <= datetime.now(UTC)


class WaRecorder:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.sent: list[tuple[str, str, str, list[str]]] = []
        self.fail = fail or set()

    async def send_template(self, phone, template, lang, body):  # noqa: ANN001
        if phone in self.fail:
            raise WhatsAppError("HTTP 400 code 131026")
        self.sent.append((phone, template, lang, body))
        return "wamid.test"


async def _second_member(client: AsyncClient, pw: str, email: str, name: str) -> dict:
    r = await client.post(f"{API}/auth/register", json={"organisation_name": f"{name} chambers", "full_name": name,
                                                         "email": email, "password": pw, "accept_terms": True})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _verified_phone(session_factory, email: str, phone: str, languages: list | None = None) -> uuid.UUID:
    async with session_factory() as s:
        user = await s.scalar(select(User).where(User.email == email))
        user.phone, user.is_phone_verified = phone, True
        if languages is not None:
            await s.execute(update(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id).values(languages=languages))
        await s.commit()
        return user.id


async def test_whatsapp_daily_is_its_own_consent_and_goes_once_to_members_who_said_yes(
    client: AsyncClient, strong_password: str, session_factory,
) -> None:
    rao = await _member(client, strong_password)                                   # says yes to the daily brief
    asha = await _second_member(client, strong_password, "asha@example.com", "Asha Verma")  # yes to product updates only
    bina = await _second_member(client, strong_password, "bina@example.com", "Bina Das")    # yes, but no verified number
    await _seed(session_factory)

    # The daily choice is separate from product updates and starts unasked.
    assert (await client.get(f"{API}/notifications/whatsapp-daily", headers=rao)).json() == {"status": "unasked", "phone_verified": False}
    await _verified_phone(session_factory, "rao@example.com", "+919876500001")
    await _verified_phone(session_factory, "asha@example.com", "+919876500002")
    yes = await client.put(f"{API}/notifications/whatsapp-daily", headers=rao, json={"granted": True, "source": "daily"})
    assert yes.status_code == 200 and yes.json() == {"status": "granted", "phone_verified": True}
    assert (await client.get(f"{API}/notifications/whatsapp-updates", headers=rao)).json()["status"] == "unasked"
    assert (await client.put(f"{API}/notifications/whatsapp-updates", headers=asha, json={"granted": True})).json()["status"] == "granted"
    assert (await client.get(f"{API}/notifications/whatsapp-daily", headers=asha)).json()["status"] == "unasked"
    assert (await client.put(f"{API}/notifications/whatsapp-daily", headers=bina, json={"granted": True})).json()["status"] == "granted"

    wa = WaRecorder()
    async with session_factory() as s:
        assert await service.send_whatsapp_briefs(s, wa, SUNDAY) == {"sent": 0, "already": 0, "failed": 0, "skipped": 0}
        assert await service.send_whatsapp_briefs(s, wa, WEDNESDAY) == {"sent": 1, "already": 0, "failed": 0, "skipped": 0}
        assert await service.send_whatsapp_briefs(s, wa, WEDNESDAY) == {"sent": 0, "already": 1, "failed": 0, "skipped": 0}
        (phone, template, lang, body), = wa.sent
        assert phone == "+919876500001" and template == "vidhisangh_daily" and lang == "en"  # Hindi: language_for, tested with product updates
        assert body[0] == "Rao" and body[1] == "Today's question"  # "Adv." dropped; the lead's title
        assert body[2].startswith(service.quiz_for(WEDNESDAY)["question"][:40]) and "\n" not in body[2]
        row = await s.scalar(select(WhatsAppCampaignSend).where(WhatsAppCampaignSend.campaign == "daily-brief-2026-11-04"))
        assert row.status == "sent" and row.template == "vidhisangh_daily" and row.basis == "consent"
        assert row.phone_hash != "+919876500001"  # the number is never stored

        # A withdrawn yes stops the next day's message; a provider refusal is recorded, not raised.
        rao_id = await s.scalar(select(User.id).where(User.email == "rao@example.com"))
        await record_choice(s, rao_id, False, "settings", None, "daily")
        await s.commit()
        assert await service.send_whatsapp_briefs(s, wa, SATURDAY) == {"sent": 0, "already": 0, "failed": 0, "skipped": 0}
        await record_choice(s, rao_id, True, "settings", None, "daily")
        await s.commit()
        failing = WaRecorder(fail={"+919876500001"})
        assert await service.send_whatsapp_briefs(s, failing, SATURDAY) == {"sent": 0, "already": 0, "failed": 1, "skipped": 0}
        failed = await s.scalar(select(WhatsAppCampaignSend).where(WhatsAppCampaignSend.campaign == "daily-brief-2026-11-07"))
        assert failed.status == "failed" and "131026" in failed.detail

    # Opening the page from the WhatsApp button is recorded as such.
    today = service.today_ist()
    r = await client.get(f"{API}/brief", headers=rao, params={"from": "whatsapp"})
    assert r.status_code == 200
    async with session_factory() as s:
        row = await s.scalar(select(DailyBriefSend).where(DailyBriefSend.for_date == today, DailyBriefSend.user_id == rao_id))
        assert row.opened_via == "whatsapp"


class MailRecorder:
    name = "email"
    configured = True

    def __init__(self, fail: bool = False) -> None:
        self.messages = []
        self.fail = fail

    async def send(self, message) -> None:  # noqa: ANN001
        self.messages.append(message)
        if self.fail:
            raise TimeoutError("SMTP acceptance unknown")


async def _verified_email(session_factory, email: str, verified: bool = True) -> uuid.UUID:
    async with session_factory() as s:
        user = await s.scalar(select(User).where(User.email == email))
        user.is_email_verified = verified
        await s.commit()
        return user.id


async def test_the_email_brief_goes_to_members_without_the_app_and_stops_on_one_tap(
    client: AsyncClient, session_factory, strong_password,
) -> None:
    with_app = await _member(client, strong_password)  # Rao has the app: no email unless asked for
    await client.post(f"{API}/notifications/devices", headers=with_app, json={"token": "fcm-" + "c" * 40, "platform": "android"})
    await _verified_email(session_factory, "rao@example.com")
    no_app = await _second_member(client, strong_password, "mehta@example.com", "Adv. Mehta")
    mehta = await _verified_email(session_factory, "mehta@example.com")
    unverified = await _second_member(client, strong_password, "new@example.com", "Adv. New")
    await _seed(session_factory)

    # Defaults: on without the app, off with it; the unverified address never gets mail.
    d = (await client.get(f"{API}/notifications/daily-email", headers=no_app)).json()
    assert d == {"enabled": True, "email_verified": True, "has_app": False, "chosen": False}
    assert (await client.get(f"{API}/notifications/daily-email", headers=with_app)).json()["enabled"] is False
    assert (await client.get(f"{API}/notifications/daily-email", headers=unverified)).json()["email_verified"] is False

    mail = MailRecorder()
    async with session_factory() as s:
        assert await service.send_email_briefs(s, mail, SUNDAY) == {"sent": 0, "already": 0, "failed": 0, "skipped": 0}
        assert await service.send_email_briefs(s, mail, WEDNESDAY) == {"sent": 1, "already": 0, "failed": 0, "skipped": 0}
        assert await service.send_email_briefs(s, mail, WEDNESDAY) == {"sent": 0, "already": 1, "failed": 0, "skipped": 0}
        await s.commit()
    assert len(mail.messages) == 1
    m = mail.messages[0]
    assert m.to_email == "mehta@example.com" and m.subject.startswith("Today's question: ")
    assert "Good morning, Mehta." in m.body and "SECTION OF THE DAY" in m.body and "Open today's brief" in m.html
    assert "/app/daily?from=email" in m.html and "Answer in the app" in m.html
    assert m.unsubscribe_url.startswith("https://vidhisangh.com/api/v1/brief/email/unsubscribe/") and m.unsubscribe_url in m.html
    assert "(A)" in m.body and "explanation" not in m.body.lower()  # the question only; the answer waits in the app

    # Opening the page from the email is recorded on the email row.
    r = await client.get(f"{API}/brief", headers=no_app, params={"from": "email", "day": WEDNESDAY.isoformat()})
    assert r.status_code == 200
    async with session_factory() as s:
        row = await s.scalar(select(DailyBriefEmail).where(DailyBriefEmail.user_id == mehta))
        assert row.status == "sent" and row.lead == "quiz" and (row.opened_at is not None) == (service.today_ist() == WEDNESDAY)

    # One tap on the unsubscribe link (POST, never GET) stops it; a member with the app can ask for it.
    token = m.unsubscribe_url.rsplit("/", 1)[-1]
    r = await client.get(f"{API}/brief/email/unsubscribe/{token}")
    assert r.status_code == 200 and "<form method='post'>" in r.text
    assert (await client.get(f"{API}/notifications/daily-email", headers=no_app)).json()["enabled"] is True
    assert (await client.post(f"{API}/brief/email/unsubscribe/{token}")).status_code == 204
    assert (await client.get(f"{API}/notifications/daily-email", headers=no_app)).json() == {
        "enabled": False, "email_verified": True, "has_app": False, "chosen": True}
    r = await client.put(f"{API}/notifications/daily-email", headers=with_app, json={"enabled": True})
    assert r.json()["enabled"] is True and r.json()["has_app"] is True
    mail = MailRecorder()
    async with session_factory() as s:
        assert await service.send_email_briefs(s, mail, SATURDAY) == {"sent": 1, "already": 0, "failed": 0, "skipped": 0}
        await s.commit()
    assert mail.messages[0].to_email == "rao@example.com" and mail.messages[0].subject.startswith("Your fraternity: ")
    # Switching on again rotates the token, so the old link cannot stop the new choice.
    r = await client.put(f"{API}/notifications/daily-email", headers=no_app, json={"enabled": True})
    assert r.json()["enabled"] is True
    assert (await client.post(f"{API}/brief/email/unsubscribe/{token}")).status_code == 204
    assert (await client.get(f"{API}/notifications/daily-email", headers=no_app)).json()["enabled"] is True
    async with session_factory() as s:
        assert len((await s.scalars(select(DailyBriefEmailPreference))).all()) == 2

    # A refusal from the mail server is recorded, not raised.
    failing = MailRecorder(fail=True)
    async with session_factory() as s:
        assert await service.send_email_briefs(s, failing, date(2026, 11, 9)) == {"sent": 0, "already": 0, "failed": 2, "skipped": 0}
        rows = (await s.scalars(select(DailyBriefEmail).where(DailyBriefEmail.for_date == date(2026, 11, 9)))).all()
        assert {r.status for r in rows} == {"failed"} and all("TimeoutError" in r.detail for r in rows)
