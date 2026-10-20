"""The official VidhiSangh account's daily feed posts.

Every morning (job ``official_posts``, about 8 am India time) the feed gets:

* **Section of the day** — a BNS / BNSS / BSA section, its opening words and
  the old-law section it replaced, linking to the public bare-act page;
* **a Supreme Court judgment** with its AI headnote summary (labelled as AI),
  linking to the public judgment page;
* **up to two official news items** from the last two days (courts, India
  Code; never LiveLaw), linking to the source.

Posts are public, so they reach every member's feed. The account is not a
user: posts carry ``OFFICIAL_AUTHOR_ID`` and the name/headline below, and the
frontend shows the logo and an "Official" mark for that id. ``official_posts``
records each section / judgment / news item once, so nothing repeats.
"""

from __future__ import annotations

import json
import random
import re
import uuid
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.html_clean import clean_html, html_to_text
from app.modules.network.models import OfficialPost, Post, PostType, PostVisibility
from app.modules.news.models import NewsItem
from app.modules.news.repository import permitted_source
from app.modules.research.models import CourtLevel, Judgment
from app.modules.research.public_pages import SITE, judgment_path

log = structlog.get_logger("app.official_posts")

OFFICIAL_AUTHOR_ID = uuid.UUID("5e1d0f00-7a1d-4e5a-9c0b-000000000001")
OFFICIAL_NAME = "VidhiSangh"
OFFICIAL_HEADLINE = "Official · Section of the day, Supreme Court judgments and legal news"
NEWS_PER_DAY = 2
NEWS_WINDOW = timedelta(days=2)
IST = ZoneInfo("Asia/Kolkata")
_SECTIONS = Path(__file__).with_name("daily_sections.json")


def _sections() -> list[dict]:
    """The pool in a fixed shuffled order (BNS, BNSS and BSA mixed)."""
    pool = json.loads(_SECTIONS.read_text(encoding="utf-8"))
    random.Random(20240701).shuffle(pool)
    return pool


async def _posted(session: AsyncSession, kind: str) -> set[str]:
    return set(await session.scalars(select(OfficialPost.ref).where(OfficialPost.kind == kind)))


async def _today(session: AsyncSession, kind: str, now: datetime) -> int:
    """How many of this kind went out today (India time)."""
    local = now.astimezone(IST)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    return int(await session.scalar(
        select(func.count()).select_from(OfficialPost).where(OfficialPost.kind == kind, OfficialPost.created_at >= start)
    ) or 0)


def _post(*, title: str, html: str, hashtags: list[str], link: dict, now: datetime) -> Post:
    cleaned = clean_html(html)
    return Post(
        author_id=OFFICIAL_AUTHOR_ID, author_name=OFFICIAL_NAME, author_headline=OFFICIAL_HEADLINE,
        post_type=PostType.ANNOUNCEMENT, title=title, content=html_to_text(cleaned)[:8000], content_html=cleaned,
        visibility=PostVisibility.PUBLIC, hashtags=hashtags,
        link_url=link["url"], link_title=link["title"][:500], link_description=(link.get("description") or "")[:600] or None,
        link_image=link.get("image"), link_site_name=link.get("site"), created_at=now,
    )


async def _record(session: AsyncSession, kind: str, ref: str, post: Post) -> None:
    session.add(post)
    await session.flush()
    session.add(OfficialPost(kind=kind, ref=ref, post_id=post.id, created_at=post.created_at))
    await session.flush()


async def post_section(session: AsyncSession, now: datetime) -> bool:
    if await _today(session, "section", now):
        return False
    done = await _posted(session, "section")
    s = next((s for s in _sections() if f"{s['act']}:{s['section']}" not in done), None)
    if s is None:
        return False
    old = f"Earlier: {s['old']}." if s["old"] else f"New in the {s['short']}: no earlier equivalent."
    html = (
        f"<p><strong>Section of the day: {escape(s['short'])} {escape(s['section'])} — {escape(s['heading'])}</strong></p>"
        f"<blockquote><p>{escape(s['text'])}</p></blockquote><p>{escape(old)}</p>"
    )
    await _record(session, "section", f"{s['act']}:{s['section']}", _post(
        title="Section of the day", html=html, hashtags=["SectionOfTheDay", s["short"]], now=now,
        link={"url": SITE + s["url"], "title": f"Section {s['section']} {s['short']} — {s['heading']}",
              "description": s["text"], "site": "VidhiSangh Bare Acts"},
    ))
    return True


def _title(j: Judgment) -> str:
    return re.sub(r"\s+", " ", j.cause_title or j.case_name).strip()


async def post_judgment(session: AsyncSession, now: datetime) -> bool:
    if await _today(session, "judgment", now):
        return False
    done = await _posted(session, "judgment")
    candidates = await session.scalars(
        select(Judgment).where(Judgment.court_level == CourtLevel.SUPREME_COURT, Judgment.ai_headnote.is_not(None))
        .order_by(Judgment.judgment_date.desc().nulls_last(), Judgment.id).limit(len(done) + 20)
    )
    j = next((j for j in candidates if str(j.id) not in done and (j.ai_headnote or {}).get("summary")), None)
    if j is None:
        return False
    summary = (j.ai_headnote or {}).get("summary") or ""
    decided = f"decided {j.judgment_date.strftime('%d/%m/%Y')}" if j.judgment_date else ""
    meta = " · ".join(x for x in (j.citation, decided) if x)
    html = (
        f"<p><strong>Supreme Court: {escape(_title(j))}</strong></p>"
        + (f"<p>{escape(meta)}</p>" if meta else "")
        + f"<p>{escape(summary)}</p>"
        + "<p><em>AI-generated summary. Read the judgment before relying on it.</em></p>"
    )
    await _record(session, "judgment", str(j.id), _post(
        title="Supreme Court judgment", html=html, hashtags=["SupremeCourt", "Judgment"], now=now,
        link={"url": SITE + judgment_path(j), "title": _title(j), "description": summary, "site": "VidhiSangh Judgments"},
    ))
    return True


async def post_news(session: AsyncSession, now: datetime) -> int:
    room = NEWS_PER_DAY - await _today(session, "news", now)
    if room <= 0:
        return 0
    done = await _posted(session, "news")
    items = (await session.scalars(
        select(NewsItem).where(NewsItem.deleted_at.is_(None), permitted_source(),
                               NewsItem.published_at >= now - NEWS_WINDOW, NewsItem.url.is_not(None))
        .order_by(NewsItem.published_at.desc()).limit(NEWS_PER_DAY + len(done) + 5)
    )).all()
    count = 0
    for n in items:
        if count >= room or str(n.id) in done:
            continue
        summary = (n.summary or "").strip()
        if len(summary) > 400:
            summary = summary[:400].rsplit(" ", 1)[0] + "…"
        html = (
            f"<p><strong>{escape(n.title)}</strong></p>"
            + (f"<p>{escape(summary)}</p>" if summary else "")
            + f"<p>Source: {escape(n.source)}</p>"
        )
        await _record(session, "news", str(n.id), _post(
            title="Legal news", html=html, hashtags=["LegalNews"], now=now,
            link={"url": n.url, "title": n.title, "description": summary, "image": n.image_url, "site": n.source},
        ))
        count += 1
    return count


async def post_daily(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """One day's official posts. Safe to rerun: each item is posted once."""
    now = now or datetime.now(UTC)
    report = {"news": await post_news(session, now)}
    # Spaced a minute apart so the feed shows the section first.
    report["judgment"] = int(await post_judgment(session, now + timedelta(minutes=1)))
    report["section"] = int(await post_section(session, now + timedelta(minutes=2)))
    log.info("official_posts", **report)
    return report
