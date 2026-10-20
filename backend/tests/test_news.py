"""Legal news feed tests — shared feed, filters, keyword search."""

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


async def _add(client: AsyncClient, h: dict, **overrides) -> dict:
    body = {
        "title": "SC clarifies arbitration seat doctrine",
        "summary": "The Court held that the seat determines supervisory jurisdiction.",
        "source": "Supreme Court",
        "category": "judgment",
        "published_at": "2026-07-10T09:00:00Z",
        "tags": ["arbitration"],
    }
    body.update(overrides)
    resp = await client.post(f"{API}/news", headers=h, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_feed_filters_and_search(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "News LLP", "news@firm.co", strong_password)
    sc = await _add(client, h)
    await _add(
        client, h,
        title="RBI circular on digital lending",
        summary="New norms for digital lending apps.",
        source="RBI", category="circular", published_at="2026-07-11T09:00:00Z", tags=["fintech"],
    )

    # Newest-first ordering.
    feed = (await client.get(f"{API}/news", headers=h)).json()
    assert [f["source"] for f in feed] == ["RBI", "Supreme Court"]

    # Category, source and keyword filters.
    assert all(f["category"] == "judgment" for f in (await client.get(f"{API}/news?category=judgment", headers=h)).json())
    rbi = (await client.get(f"{API}/news?source=RBI", headers=h)).json()
    assert len(rbi) == 1
    hit = (await client.get(f"{API}/news?q=arbitration", headers=h)).json()
    assert [f["id"] for f in hit] == [sc["id"]]
    assert (await client.get(f"{API}/news?q=zzznope", headers=h)).json() == []


async def test_news_is_shared_across_tenants(client: AsyncClient, strong_password: str) -> None:
    a_h, _ = await _user(client, "Firm A", "na@firma.co", strong_password)
    b_h, _ = await _user(client, "Firm B", "nb@firmb.co", strong_password)
    item = await _add(client, a_h, title="Gazette notification on GST rates", source="Gazette")

    seen = (await client.get(f"{API}/news?q=gazette", headers=b_h)).json()
    assert any(f["id"] == item["id"] for f in seen)


async def test_competitor_excluded_from_list_and_detail(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Source check", "source@firm.co", strong_password)
    competitor = await _add(client, h, source="Live Law", url="https://www.livelaw.in/example")
    official = await _add(client, h, source="Supreme Court of India", url="https://www.sci.gov.in/")
    feed = (await client.get(f"{API}/news", headers=h)).json()
    assert [row["id"] for row in feed] == [official["id"]]
    assert "image_url" in feed[0]
    assert (await client.get(f"{API}/news/{competitor['id']}", headers=h)).status_code == 404


async def test_official_parser_only_accepts_dated_judgment_links() -> None:
    from app.scripts.ingest_official_news import SupremeCourtParser
    parser = SupremeCourtParser()
    parser.feed('''<a href="https://www.sci.gov.in/view-pdf/?type=j&amp;order_date=2026-09-25&amp;diary_no=123">A <b>VS.</b> B</a>
    <a href="https://www.livelaw.in/view-pdf/?type=j&amp;order_date=2026-09-25">Competitor</a>
    <a href="/view-pdf/?type=j&amp;order_date=invalid">Invalid</a>
    <a href="/view-pdf/?type=o&amp;order_date=2026-09-25">Order</a>''')
    assert len(parser.entries) == 1
    item = parser.entries[0]
    assert item.title == "A VS. B"
    assert item.category == "judgment"
    assert item.published_at.isoformat() == "2026-09-25T00:00:00+00:00"


async def test_official_update_category_classification() -> None:
    from app.scripts.ingest_official_news import Entry, SupremeCourtParser, image_for
    from datetime import UTC, datetime
    parser = SupremeCourtParser()
    parser.feed('''<a class="content-view-sci" href="https://cdnbbsr.s3waas.gov.in/uploads/2026/09/2026092501.pdf">
      <span>AOR - Notices and Circulars</span><span>Notification regarding examination</span></a>
      <a class="content-view-sci" href="https://cdnbbsr.s3waas.gov.in/uploads/2026/09/2026092502.pdf">
      <span>Latest Updates</span><span>New digital service launched</span></a>''')
    assert [item.category for item in parser.entries] == ["notification", "news"]
    base = dict(title="Item", url="https://official.example/item", published_at=datetime.now(UTC), summary="Summary", tags=[])
    assert "state-high-court" in image_for(Entry(source="High Court of Delhi", category="judgment", **base))
    assert "legislation" in image_for(Entry(source="India Code", category="legislation", **base))
    assert "official-notice" in image_for(Entry(source="Supreme Court of India", category="circular", **base))
    assert "justice-editorial" in image_for(Entry(source="Supreme Court of India", category="judgment", **base))


def test_more_official_sources_read_their_dated_notices() -> None:
    from datetime import UTC, datetime, timedelta

    from app.scripts.ingest_official_news import (
        AllahabadHighCourtParser,
        LawCommissionParser,
        NalsaParser,
        PunjabHaryanaHighCourtParser,
    )

    recent = datetime.now(UTC) - timedelta(days=10)
    dmy, ymd = recent.strftime("%d-%m-%Y"), recent.strftime("%Y%m%d")

    p = AllahabadHighCourtParser()
    p.feed(f'<a href="/event/event_26322_{dmy}.pdf">Publication of Revised Advocates\' Chambers Rules, 2026</a>'
           '<a href="/event/event_9302_16-04-2021.pdf">Video Conferencing guidelines of 2021</a>'
           f'<a href="/event/event_1_{dmy}.pdf">Tender for supply of furniture to the court</a>')
    assert [(e.title, e.url) for e in p.entries] == [
        ("Publication of Revised Advocates' Chambers Rules, 2026", f"https://www.allahabadhighcourt.in/event/event_26322_{dmy}.pdf")]
    assert p.entries[0].published_at.date() == recent.date()  # old and tender notices left out

    p = PunjabHaryanaHighCourtParser()
    p.feed(f'<a href="https://highcourtchd.gov.in/sub_pages/left_menu/publish/announce/announce_pdf/gowns_{recent:%d%m%Y}_ab12.pdf">'
           'Notice regarding wearing of gowns w.e.f. 02.11.2026</a><a href="./sub_pages/x/Roster_crnt.pdf">Judges Roster</a>')
    assert [e.title for e in p.entries] == ["Notice regarding wearing of gowns w.e.f. 02.11.2026"]
    assert p.entries[0].source == "High Court of Punjab and Haryana" and p.entries[0].category == "circular"

    p = NalsaParser()
    p.feed(f'<a href="https://cdnbbsr.s3waas.gov.in/s32e45/uploads/{ymd[:4]}/{ymd[4:6]}/{ymd}1181865580.pdf">Digital Media Internship - 2026  New</a>')
    assert [e.title for e in p.entries] == ["Digital Media Internship - 2026"]

    p = LawCommissionParser()
    p.feed('<table><tr><th>Sr. No.</th><th>Title</th><th>Description</th><th>Start Date</th><th>End Date</th><th>File</th></tr>'
           f'<tr><td>1</td><td>JUDGEMENTS AND GENDER (Sensitivity and compassion in writing judgments)</td><td></td><td>{recent:%d/%m/%Y}</td>'
           '<td>31/08/2027</td><td><a href="https://cdnbbsr.s3waas.gov.in/s3ca/uploads/2026/08/2026081930.pdf">View</a></td></tr></table>')
    assert [(e.title, e.source) for e in p.entries] == [
        ("JUDGEMENTS AND GENDER (Sensitivity and compassion in writing judgments)", "Law Commission of India")]
    assert p.entries[0].published_at.date() == recent.date()
