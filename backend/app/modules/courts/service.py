"""Court desk: the cause lists a court published, posted to the court's group and
shown on the Daily page to members of that court.

Built 16 November 2026 after the owner asked for "a daily cause list and court
details, without using any personal data, for their respective courts". Only
public index pages are read (``fetch.py``); a member's court is taken from their
own profile (the courts they list, their headline, state) purely to pick which
card to show them, and nothing about a member is ever sent to a court site.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.html_clean import clean_html, html_to_text
from app.modules.courts import fetch as fetching
from app.modules.courts.models import CourtCauseList
from app.modules.courts.registry import BY_SLUG, COURTS, ECOURTS_HC, Court
from app.modules.groups.models import Group, GroupPost
from app.modules.groups.official import court_group_slug
from app.modules.network.official import OFFICIAL_AUTHOR_ID, OFFICIAL_NAME
from app.modules.profile.models import ProfessionalProfile

log = structlog.get_logger("app.court_desk")
IST = ZoneInfo("Asia/Kolkata")
SUPREME_COURT = "supreme-court-of-india"


def today_ist(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(IST).date()


def court_for_profile(profile: ProfessionalProfile | None) -> Court | None:
    """The court a member belongs to, from their own profile: the courts they list
    first, then the headline the invitation set ("Advocate, Allahabad High
    Court"), then bar council and state. Generic entries ("High Court",
    "Family Court") match nothing."""
    if profile is None:
        return None
    candidates = [*(c for c in (profile.courts or []) if isinstance(c, str)),
                  profile.headline, profile.bar_council, profile.state]
    for text in candidates:
        slug = court_group_slug(text)
        if slug in BY_SLUG:
            return BY_SLUG[slug]
    return None


# ── The job ─────────────────────────────────────────────────────────────
async def refresh(session: AsyncSession, http: httpx.AsyncClient, today: date) -> dict[str, int]:
    """Read every fetchable court's index and record the lists for today and
    later days (one row per court and day; a row is updated when the court
    adds a list, e.g. a supplementary one). A court whose site fails reports
    -1 and the others still run."""
    report: dict[str, int] = {}
    now = datetime.now(UTC)
    for court in COURTS:
        if not court.fetcher:
            continue
        try:
            found = await fetching.fetch(http, court)
        except Exception as exc:  # noqa: BLE001 — a court site being down must not stop the rest
            log.warning("court_desk_fetch_failed", court=court.slug, error=f"{type(exc).__name__}: {exc}"[:200])
            report[court.slug] = -1
            continue
        changed = 0
        for day, lists in sorted(found.items()):
            if day < today or not lists:
                continue
            row = await session.scalar(select(CourtCauseList).where(
                CourtCauseList.court_slug == court.slug, CourtCauseList.for_date == day))
            if row is None:
                session.add(CourtCauseList(court_slug=court.slug, for_date=day, lists=lists,
                                           source_url=court.cause_list_url, fetched_at=now))
                changed += 1
            elif row.lists != lists:
                row.lists, row.fetched_at = lists, now
                changed += 1
        await session.flush()
        report[court.slug] = changed
        log.info("court_desk_fetched", court=court.slug, days=len(found), changed=changed)
    return report


def _when(for_date: date, today: date) -> str:
    if for_date == today:
        return "today"
    if for_date == today + timedelta(days=1):
        return "tomorrow"
    return for_date.strftime("%A")


def post_body(court: Court, row: CourtCauseList, today: date) -> tuple[str, str]:
    """Text and HTML for the group post announcing a day's lists."""
    when = _when(row.for_date, today)
    heading = f"Cause list for {when}, {row.for_date.strftime('%A %d/%m/%Y')}"
    items = "".join(f'<li><a href="{escape(l["url"])}">{escape(l["label"])}</a></li>' for l in row.lists)
    html = (f"<p><strong>{escape(heading)}</strong></p><ul>{items}</ul>"
            f'<p><a href="{escape(court.cause_list_url)}">All cause lists on the {escape(court.name)} website</a></p>')
    cleaned = clean_html(html)
    return html_to_text(cleaned)[:8000], cleaned


async def post_new(session: AsyncSession, now: datetime | None = None) -> int:
    """One post per court and listing day in the court's official group, by the
    official account, the first time the day's lists are seen, for today and
    tomorrow only: the Supreme Court publishes advance lists two weeks ahead,
    which are recorded (the card shows the next listing day) but would be noise
    as posts. Days already past are left alone (a run missed for a day never
    posts stale lists)."""
    today = today_ist(now)
    rows = (await session.scalars(
        select(CourtCauseList).where(
            CourtCauseList.group_post_id.is_(None),
            CourtCauseList.for_date >= today, CourtCauseList.for_date <= today + timedelta(days=1))
        .order_by(CourtCauseList.for_date, CourtCauseList.court_slug)
    )).all()
    posted = 0
    for row in rows:
        court = BY_SLUG.get(row.court_slug)
        if court is None:
            continue
        group = await session.scalar(select(Group).where(Group.slug == court.slug, Group.deleted_at.is_(None)))
        if group is None:
            continue
        text, html = post_body(court, row, today)
        post = GroupPost(group_id=group.id, author_id=OFFICIAL_AUTHOR_ID, author_name=OFFICIAL_NAME,
                         content=text, content_html=html)
        session.add(post)
        group.post_count += 1
        await session.flush()
        row.group_post_id = post.id
        posted += 1
    await session.flush()
    if posted:
        log.info("court_desk_posted", posts=posted)
    return posted


# ── The card ────────────────────────────────────────────────────────────
def _day(row: CourtCauseList | None) -> dict | None:
    return None if row is None else {"for_date": row.for_date, "lists": row.lists, "fetched_at": row.fetched_at}


async def card_for(session: AsyncSession, court: Court, day: date) -> dict:
    rows = (await session.scalars(
        select(CourtCauseList).where(CourtCauseList.court_slug == court.slug, CourtCauseList.for_date >= day)
        .order_by(CourtCauseList.for_date).limit(2)
    )).all()
    group_id: uuid.UUID | None = await session.scalar(
        select(Group.id).where(Group.slug == court.slug, Group.deleted_at.is_(None)))
    return {
        "slug": court.slug, "name": court.name, "website": court.website, "cause_list_url": court.cause_list_url,
        "ecourts_url": None if court.slug == SUPREME_COURT else ECOURTS_HC,
        "group_id": group_id, "fetches": bool(court.fetcher),
        "today": _day(next((r for r in rows if r.for_date == day), None)),
        "next": _day(next((r for r in rows if r.for_date > day), None)),
    }
