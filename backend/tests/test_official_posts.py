"""Official VidhiSangh feed posts: Section of the day, a Supreme Court judgment, legal news."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.modules.network import official
from app.modules.network.models import OfficialPost, Post
from app.modules.news.models import NewsCategory, NewsItem
from app.modules.research.models import CourtLevel, Judgment

pytestmark = pytest.mark.asyncio
API = "/api/v1"
NOW = datetime(2026, 10, 21, 2, 30, tzinfo=UTC)  # 8 am in India
HEADNOTE = {"summary": "Bail cannot be refused only because the charge sheet is long.", "issues": ["x"],
            "provisions": [], "held": [{"point": "y", "paragraphs": ["1"]}], "result": "Allowed."}


async def _member(client: AsyncClient, pw: str) -> dict:
    r = await client.post(f"{API}/auth/register", json={"organisation_name": "Rao Chambers", "full_name": "Adv. Rao",
                                                         "email": "rao@example.com", "password": pw, "accept_terms": True})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _seed(session_factory) -> dict[str, uuid.UUID]:
    ids = {}
    actor = uuid.UUID(int=0)
    async with session_factory() as s:
        for key, level, day, headnote in (
            ("newest", CourtLevel.SUPREME_COURT, date(2026, 10, 1), HEADNOTE),
            ("older", CourtLevel.SUPREME_COURT, date(2025, 1, 1), HEADNOTE),
            ("plain", CourtLevel.SUPREME_COURT, date(2026, 10, 10), None),
            ("hc", CourtLevel.HIGH_COURT, date(2026, 10, 15), HEADNOTE),
        ):
            j = Judgment(case_name=f"{key.title()} v. State", citation=f"[2026] {key}", court="Court", court_level=level,
                         judgment_date=day, ai_headnote=headnote, added_by=actor)
            s.add(j)
            await s.flush()
            ids[key] = j.id
        for key, source, url, age in (
            ("fresh", "Supreme Court of India", "https://www.sci.gov.in/notice-1", timedelta(hours=5)),
            ("livelaw", "LiveLaw", "https://www.livelaw.in/x", timedelta(hours=1)),
            ("stale", "High Court of Delhi", "https://delhihighcourt.nic.in/old", timedelta(days=5)),
        ):
            n = NewsItem(title=f"{key.title()} notice", summary="A circular on e-filing.", source=source,
                         category=NewsCategory.NOTIFICATION, url=url, published_at=NOW - age, tags=[], added_by=actor)
            s.add(n)
            await s.flush()
            ids[key] = n.id
        await s.commit()
    return ids


async def test_a_morning_of_official_posts_reaches_every_feed_once(
    client: AsyncClient, strong_password: str, session_factory,
) -> None:
    h = await _member(client, strong_password)
    ids = await _seed(session_factory)
    async with session_factory() as s:
        assert await official.post_daily(s, NOW) == {"news": 1, "judgment": 1, "section": 1}
        await s.commit()

    feed = (await client.get(f"{API}/network/feed", headers=h)).json()
    official_posts = [p for p in feed if p["author_id"] == str(official.OFFICIAL_AUTHOR_ID)]
    assert [p["title"] for p in official_posts] == ["Section of the day", "Supreme Court judgment", "Legal news"]
    section, judgment, news = official_posts
    assert section["author_name"] == "VidhiSangh" and section["visibility"] == "public"
    assert section["content_html"].startswith("<p><strong>Section of the day: ")
    assert section["link_url"].startswith("https://vidhisangh.com/acts/") and section["link_site_name"] == "VidhiSangh Bare Acts"
    assert "Newest v. State" in judgment["content_html"] and "AI-generated summary" in judgment["content_html"]
    assert judgment["link_url"] == f"https://vidhisangh.com/judgments/{ids['newest']}/newest-v-state/"
    assert news["link_url"] == "https://www.sci.gov.in/notice-1" and "Source: Supreme Court of India" in news["content_html"]

    # Rerun the same morning: nothing more.
    async with session_factory() as s:
        assert await official.post_daily(s, NOW + timedelta(hours=3)) == {"news": 0, "judgment": 0, "section": 0}
        await s.commit()

    # Next morning: the next judgment and a different section; no news left.
    async with session_factory() as s:
        assert await official.post_daily(s, NOW + timedelta(days=1)) == {"news": 0, "judgment": 1, "section": 1}
        await s.commit()
        refs = {(o.kind, o.ref) for o in await s.scalars(select(OfficialPost))}
        assert ("judgment", str(ids["older"])) in refs
        assert ("judgment", str(ids["hc"])) not in refs and ("judgment", str(ids["plain"])) not in refs
        assert ("news", str(ids["livelaw"])) not in refs and ("news", str(ids["stale"])) not in refs
        assert len([r for r in refs if r[0] == "section"]) == 2
        assert await s.scalar(select(Post.id).where(Post.author_id == official.OFFICIAL_AUTHOR_ID).limit(1))


def test_the_section_pool_covers_the_three_new_laws() -> None:
    pool = official._sections()
    assert len(pool) > 1000
    assert {s["act"] for s in pool} == {"bns", "bnss", "bsa"}
    cheating = next(s for s in pool if s["act"] == "bns" and s["section"] == "318")
    assert cheating["heading"] == "Cheating" and "IPC" in cheating["old"] and "420" in cheating["old"]
    assert all(s["url"].startswith(f"/acts/{s['act']}/section-") for s in pool)


async def test_daily_cards_for_the_home_screen(client: AsyncClient, strong_password: str, session_factory) -> None:
    h = await _member(client, strong_password)
    empty = (await client.get(f"{API}/network/daily", headers=h)).json()
    assert empty == {"section": None, "judgment": None, "news": []}
    ids = await _seed(session_factory)
    async with session_factory() as s:
        await official.post_daily(s, NOW)
        await s.commit()
    daily = (await client.get(f"{API}/network/daily", headers=h)).json()
    assert daily["section"]["kind"] == "section" and ":" in daily["section"]["ref"]
    assert daily["section"]["title"].startswith("Section ")
    assert daily["judgment"]["ref"] == str(ids["newest"]) and "Bail cannot be refused" in daily["judgment"]["description"]
    assert len(daily["news"]) == 1 and daily["news"][0]["url"]
    assert (await client.get(f"{API}/network/daily")).status_code == 401
