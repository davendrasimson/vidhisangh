"""VidhiSangh Daily: the page, the quiz, the landmark picker and the morning push."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.push import PushMessage
from app.modules.brief import service
from app.modules.brief.models import DailyBriefSend, DailyQuizAnswer
from app.modules.network import official
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
        # 3 June in two earlier years: the one cited more wins the fallback.
        a = Judgment(case_name="ALPHA versus STATE", court="Supreme Court", court_level=CourtLevel.SUPREME_COURT,
                     judgment_date=date(1990, 6, 3), ai_headnote={**HEADNOTE, "summary": "Alpha holding."}, added_by=actor)
        b = Judgment(case_name="BETA versus STATE", court="Supreme Court", court_level=CourtLevel.SUPREME_COURT,
                     judgment_date=date(2001, 6, 3), ai_headnote={**HEADNOTE, "summary": "Beta holding."}, added_by=actor)
        plain = Judgment(case_name="GAMMA versus STATE", court="Supreme Court", court_level=CourtLevel.SUPREME_COURT,
                         judgment_date=date(2005, 6, 3), added_by=actor)
        s.add_all([k, a, b, plain])
        await s.flush()
        from app.modules.research.models import CaseCitation, CitationRelationship
        for _ in range(2):
            s.add(CaseCitation(from_judgment_id=plain.id, to_judgment_id=a.id, relationship_type=CitationRelationship.REFERRED, added_by=actor))
        s.add(CaseCitation(from_judgment_id=plain.id, to_judgment_id=b.id, relationship_type=CitationRelationship.REFERRED, added_by=actor))
        await s.commit()
        kid, aid = k.id, a.id

    async with session_factory() as s:
        curated = await service.on_this_day(s, date(2027, 4, 24))
        assert curated["source"] == "curated" and curated["judgment_id"] == kid and curated["decided"] == date(1973, 4, 24)
        corpus = await service.on_this_day(s, date(2027, 6, 3))
        assert corpus["source"] == "corpus" and corpus["judgment_id"] == aid and corpus["holding"] == "Alpha holding."
        assert corpus["case"] == "Alpha v. State"
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
