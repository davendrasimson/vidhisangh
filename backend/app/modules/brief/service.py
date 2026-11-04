"""VidhiSangh Daily: one brief a day, built from what the platform already has.

Every day (India time) has the same six items, and the **lead** rotates by
weekday so the morning message is never the same two days running:

* Monday    — Section of the day (BNS / BNSS / BSA, with the old-law number)
* Tuesday   — Supreme Court judgment of the day (AI headnote)
* Wednesday — one quiz question (answer revealed in the app)
* Thursday  — On this day: a landmark judgment decided on this date
* Friday    — legal news
* Saturday  — the fraternity: who joined near you
* Sunday    — no message; the page still works (lead: on this day)

The section, judgment and news come from the official account's posts
(``network.official``), so the brief and the feed agree. The quiz bank and the
curated landmark list are JSON files beside this module; both were checked
against the judgment corpus before going live. Days without a curated landmark
take the most-cited Supreme Court judgment with an AI headnote decided on that
date in any earlier year.

The ``daily_brief`` job (07:30 IST, Monday to Saturday) pushes the lead to every
member with the app; ``daily_brief_sends`` is claimed before each push so a
rerun never sends twice, and records who opened the page. Quiz answers are
stored once per member and question.
"""

from __future__ import annotations

import json
import random
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import apply_rls_context
from app.core.push import PushMessage, PushSender
from app.modules.brief.models import DailyBriefSend, DailyQuizAnswer
from app.modules.identity.models import User
from app.modules.network.models import NetworkIdentity
from app.modules.network.official import case_title, daily_cards, post_daily
from app.modules.network.repository import IdentityRepository
from app.modules.notifications.models import NotificationChannel, NotificationPreference, PushDevice
from app.modules.research.models import CourtLevel, Judgment, JudgmentAlias

log = structlog.get_logger("app.daily_brief")
IST = ZoneInfo("Asia/Kolkata")
EPOCH = date(2026, 11, 4)           # day 0 of the quiz rotation
SHUFFLE_SEED = 20261104
LEADS = {0: "section", 1: "judgment", 2: "quiz", 3: "on_this_day", 4: "news", 5: "fraternity", 6: "on_this_day"}
PUSH_WEEKDAYS = range(0, 6)         # Monday to Saturday
PAGE = "/app/daily"
MIN_CITED = 3                       # corpus fallback needs this many later citations
_HERE = Path(__file__).parent
_quiz_cache: list[dict] | None = None
_landmark_cache: list[dict] | None = None


def today_ist(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(IST).date()


def lead_for(day: date) -> str:
    return LEADS[day.weekday()]


def pushes_on(day: date) -> bool:
    return day.weekday() in PUSH_WEEKDAYS


# ── Quiz ────────────────────────────────────────────────────────────────
def quiz_bank() -> list[dict]:
    """The questions in a fixed shuffled order; the day's index walks through it and wraps."""
    global _quiz_cache
    if _quiz_cache is None:
        pool = json.loads((_HERE / "daily_quiz.json").read_text(encoding="utf-8"))
        random.Random(SHUFFLE_SEED).shuffle(pool)
        _quiz_cache = pool
    return _quiz_cache


def quiz_for(day: date) -> dict:
    bank = quiz_bank()
    return bank[(day.toordinal() - EPOCH.toordinal()) % len(bank)]


def quiz_by_id(quiz_id: str) -> dict | None:
    return next((q for q in quiz_bank() if q["id"] == quiz_id), None)


async def quiz_stats(session: AsyncSession, quiz_id: str) -> dict[str, int]:
    row = (await session.execute(
        select(func.count(), func.count().filter(DailyQuizAnswer.correct.is_(True)))
        .where(DailyQuizAnswer.quiz_id == quiz_id)
    )).one()
    return {"answers": int(row[0] or 0), "right": int(row[1] or 0)}


async def quiz_view(session: AsyncSession, day: date, user_id: uuid.UUID | None) -> dict:
    """The day's question as the page shows it: the answer only after this member has answered."""
    q = quiz_for(day)
    view = {"id": q["id"], "topic": q["topic"], "question": q["question"], "options": q["options"], "link": q.get("link"),
            "chosen": None, "answer": None, "explanation": None, "stats": await quiz_stats(session, q["id"])}
    if user_id is not None:
        mine = await session.scalar(select(DailyQuizAnswer).where(
            DailyQuizAnswer.user_id == user_id, DailyQuizAnswer.quiz_id == q["id"]))
        if mine is not None:
            view.update(chosen=mine.chosen, answer=q["answer"], explanation=q["explanation"])
    return view


async def answer_quiz(session: AsyncSession, user_id: uuid.UUID, quiz_id: str, chosen: int, day: date) -> dict | None:
    """Records the member's one attempt (a second call returns the first answer). None for an unknown question."""
    q = quiz_by_id(quiz_id)
    if q is None or not 0 <= chosen < len(q["options"]):
        return None
    row = await session.scalar(select(DailyQuizAnswer).where(
        DailyQuizAnswer.user_id == user_id, DailyQuizAnswer.quiz_id == quiz_id))
    if row is None:
        row = DailyQuizAnswer(user_id=user_id, quiz_id=quiz_id, for_date=day, chosen=chosen, correct=chosen == q["answer"])
        session.add(row)
        await session.flush()
    return {"quiz_id": quiz_id, "chosen": row.chosen, "answer": q["answer"], "correct": row.correct,
            "explanation": q["explanation"], "stats": await quiz_stats(session, quiz_id), "answered_at": row.created_at}


# ── On this day ─────────────────────────────────────────────────────────
def landmarks() -> list[dict]:
    global _landmark_cache
    if _landmark_cache is None:
        _landmark_cache = json.loads((_HERE / "daily_landmarks.json").read_text(encoding="utf-8"))
    return _landmark_cache


def landmark_for(day: date) -> dict | None:
    """The curated landmark for this month-day; with several, the year picks one so they rotate."""
    same = [e for e in landmarks() if e["date"][5:] == day.strftime("%m-%d")]
    if not same:
        return None
    return same[day.year % len(same)]


def _name_column():
    return func.lower(func.coalesce(Judgment.cause_title, Judgment.case_name))


async def on_this_day(session: AsyncSession, day: date) -> dict | None:
    curated = landmark_for(day)
    if curated is not None:
        decided = date.fromisoformat(curated["date"])
        # The corpus copy, for the link; a day or two of slack covers registry date differences.
        jid = await session.scalar(
            select(Judgment.id).where(
                Judgment.court_level == CourtLevel.SUPREME_COURT,
                Judgment.judgment_date.between(date.fromordinal(decided.toordinal() - 2), date.fromordinal(decided.toordinal() + 2)),
                _name_column().like(f"%{curated['match'].lower()}%"),
            ).order_by(Judgment.judgment_date).limit(1)
        )
        return {"case": curated["case"], "decided": decided, "citation": curated.get("citation"),
                "holding": curated["holding"], "judgment_id": jid, "source": "curated"}
    # Otherwise the Supreme Court judgment decided on this date in any earlier year that later judgments
    # cite most (the mined citation aliases' support counts), when there is a clear signal.
    dates = []
    for year in range(1950, day.year):
        try:
            dates.append(date(year, day.month, day.day))
        except ValueError:
            continue  # 29 February
    if not dates:
        return None
    cited = (select(JudgmentAlias.judgment_id, func.sum(JudgmentAlias.support).label("n"))
             .group_by(JudgmentAlias.judgment_id).subquery())
    row = (await session.execute(
        select(Judgment, cited.c.n)
        .join(cited, cited.c.judgment_id == Judgment.id)
        .where(Judgment.court_level == CourtLevel.SUPREME_COURT, Judgment.judgment_date.in_(dates), cited.c.n >= MIN_CITED)
        .order_by(cited.c.n.desc(), Judgment.judgment_date.asc()).limit(1)
    )).first()
    if row is None:
        return None
    j: Judgment = row[0]
    n = int(row[1] or 0)
    holding, basis = _holding(j, n)
    return {"case": case_title(j.cause_title or j.case_name), "decided": j.judgment_date, "citation": j.citation,
            "holding": holding, "judgment_id": j.id, "source": "corpus", "basis": basis, "cited": n}


def _holding(j: Judgment, cited: int) -> tuple[str, str]:
    """The one-paragraph holding: the AI headnote's summary (basis 'ai'); without one, what we can say for
    certain (basis 'cited'). The registry's ``headnote`` column is a fragment of the text, not a holding,
    so it is never shown."""
    ai = (j.ai_headnote or {}).get("summary") or (j.ai_headnote or {}).get("result")
    if ai:
        return ai.strip(), "ai"
    return (f"Of the Supreme Court judgments decided on this date, this is the one later judgments cite most: "
            f"{cited} citations in the VidhiSangh corpus. Open it to read what it decided."), "cited"


# ── The brief ───────────────────────────────────────────────────────────
async def compose(session: AsyncSession, day: date, user_id: uuid.UUID | None) -> dict:
    """Everything on the page except the fraternity card, which needs the viewer's network identity
    (the router adds it). ``user_id`` personalises the quiz (answered or not)."""
    cards = await daily_cards(session)
    return {
        "day": day, "weekday": day.strftime("%A"), "lead": lead_for(day),
        "section": cards["section"], "judgment": cards["judgment"], "news": cards["news"],
        "quiz": await quiz_view(session, day, user_id),
        "on_this_day": await on_this_day(session, day),
    }


async def mark_opened(session: AsyncSession, user_id: uuid.UUID, day: date, via: str) -> None:
    """The member opened the page: note it on the day's send row (or add a 'viewed' row without a push)."""
    row = await session.scalar(select(DailyBriefSend).where(DailyBriefSend.user_id == user_id, DailyBriefSend.for_date == day))
    if row is None:
        session.add(DailyBriefSend(user_id=user_id, for_date=day, lead=lead_for(day), status="viewed",
                                   opened_at=datetime.now(UTC), opened_via=via))
    elif row.opened_at is None:
        row.opened_at, row.opened_via = datetime.now(UTC), via
    await session.flush()


# ── The morning push ────────────────────────────────────────────────────
def _clean(value: str | None, limit: int) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _message(lead: str, brief: dict, fraternity: dict | None) -> tuple[str, str] | None:
    """Title and body for the push, by lead. None when the lead item is missing today."""
    if lead == "section" and brief["section"]:
        return "Section of the day", _clean(brief["section"]["title"], 140)
    if lead == "judgment" and brief["judgment"]:
        j = brief["judgment"]
        return "Supreme Court, judgment of the day", _clean(f"{j['title']}. {j.get('description') or ''}", 180)
    if lead == "quiz":
        return "Today's question", _clean(brief["quiz"]["question"], 180)
    if lead == "on_this_day" and brief["on_this_day"]:
        o = brief["on_this_day"]
        return f"On this day in {o['decided'].year}", _clean(f"{o['case']}: {o['holding']}", 180)
    if lead == "news" and brief["news"]:
        return "The week in law", _clean("; ".join(n["title"] for n in brief["news"][:3]), 180)
    if lead == "fraternity" and fraternity:
        joined, city, in_city = fraternity["joined_7d"], fraternity.get("city"), fraternity["in_city"]
        who = f"{joined} advocate{'s' if joined != 1 else ''} joined this week"
        if city and in_city:
            who += f", {in_city} in {city}"
        return "Your fraternity", who + ". See who to connect with."
    return None


async def recipients(session: AsyncSession) -> list[User]:
    """Members with the app and push allowed. Needs RLS bypass."""
    push_off = set(await session.scalars(select(NotificationPreference.user_id).where(
        NotificationPreference.channel == NotificationChannel.PUSH, NotificationPreference.enabled.is_(False))))
    with_app = set(await session.scalars(select(PushDevice.user_id).distinct())) - push_off
    if not with_app:
        return []
    return list(await session.scalars(select(User).where(
        User.id.in_(with_app), User.deleted_at.is_(None), User.is_active.is_(True))))


async def _fraternity_counts(session: AsyncSession, user_id: uuid.UUID) -> dict:
    city = await session.scalar(select(NetworkIdentity.city).where(NetworkIdentity.user_id == user_id))
    counts = await IdentityRepository(session).counts(city, datetime.now(UTC) - __import__("datetime").timedelta(days=7))
    return {**counts, "city": city}


async def _commit(session: AsyncSession) -> None:
    """Commit and keep working across tenants. The RLS bypass is transaction-local (``set_config(...,
    is_local)``), so a plain commit would leave the next query (``users`` is tenant-scoped) seeing nothing:
    the first live run on 4 November 2026 pushed to nobody for exactly this reason."""
    await session.commit()
    await apply_rls_context(session, None, bypass=True)


async def send_briefs(session: AsyncSession, push: PushSender, day: date) -> dict[str, int]:
    """Pushes the day's lead to every member with the app, once. Posts the day's official items first
    (idempotent) so the section and judgment exist before anyone is told about them."""
    report = {"sent": 0, "already": 0, "failed": 0, "skipped": 0}
    if not pushes_on(day):
        log.info("daily_brief_quiet_day", day=day.isoformat())
        return report
    await post_daily(session)
    await _commit(session)
    lead = lead_for(day)
    brief = await compose(session, day, None)
    for user in await recipients(session):
        exists = await session.scalar(select(DailyBriefSend.id).where(
            DailyBriefSend.user_id == user.id, DailyBriefSend.for_date == day, DailyBriefSend.status != "viewed"))
        if exists:
            report["already"] += 1
            continue
        fraternity = await _fraternity_counts(session, user.id) if lead == "fraternity" else None
        message = _message(lead, brief, fraternity)
        if message is None:
            report["skipped"] += 1
            continue
        row = await session.scalar(select(DailyBriefSend).where(DailyBriefSend.user_id == user.id, DailyBriefSend.for_date == day))
        if row is None:
            row = DailyBriefSend(user_id=user.id, for_date=day, lead=lead, status="sending")
            session.add(row)
        else:  # a 'viewed' row from an early visit: the push still goes
            row.status, row.lead = "sending", lead
        await _commit(session)
        title, body = message
        sent = 0
        for device in (await session.scalars(select(PushDevice).where(PushDevice.user_id == user.id))).all():
            result = await push.send(device.token, PushMessage(title=title, body=body, link=f"{PAGE}?from=push&lead={lead}"))
            if result == "sent":
                sent += 1
            elif result == "unregistered":
                await session.delete(device)
        row.status = "sent" if sent else "failed"
        row.detail = f"push x{sent}" if sent else "push: not delivered"
        report["sent" if sent else "failed"] += 1
        await _commit(session)
    log.info("daily_brief", day=day.isoformat(), lead=lead, **report)
    return report
