"""AI-generated headnotes (migration 0064): queue order, import validation, the flag."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from tests.test_research import API, _user

HEADNOTE = {
    "summary": "Input tax credit cannot be denied for a procedural lapse when the tax was paid.",
    "issues": ["Whether Section 16(4) bars credit claimed after the due date"],
    "provisions": [{
        "act": "Central Goods and Services Tax Act, 2017",
        "provision": "Section 16(4)",
        "how_applied": "Read with the extension notified for the period; the claim fell within time.",
        "paragraphs": ["12", "14"],
    }],
    "held": [{"point": "The claim was within the extended period, so the credit was wrongly denied.", "paragraphs": ["15"]}],
    "result": "Appeal allowed.",
}


async def _seed(session_factory) -> dict[str, uuid.UUID]:
    from app.modules.identity.models import User
    from app.modules.research.models import CourtLevel, Judgment

    ids = {}
    async with session_factory() as session:
        user_id = (await session.execute(select(User.id).limit(1))).scalar_one()
        rows = [
            ("old", CourtLevel.SUPREME_COURT, date(2020, 1, 5), "Body of an old judgment."),
            ("new", CourtLevel.SUPREME_COURT, date(2026, 8, 12),
             "[2026] 8 S.C.R. 1 EDITORIAL HEADNOTE the reporter wrote Case Arising From CIVIL APPELLATE "
             "JURISDICTION: Civil Appeal No. 1 of 2026. JUDGMENT 1. The appeal is allowed."),
            ("mid", CourtLevel.SUPREME_COURT, date(2024, 3, 1), "Body of a 2024 judgment."),
            ("notext", CourtLevel.SUPREME_COURT, date(2026, 9, 1), None),
            ("hc", CourtLevel.HIGH_COURT, date(2026, 9, 2), "High Court order text."),
        ]
        for key, level, day, text in rows:
            j = Judgment(case_name=f"{key} v. State", citation=f"[{key}]", court="Court", court_level=level,
                         judgment_date=day, full_text=text, added_by=user_id)
            session.add(j)
            await session.flush()
            ids[key] = j.id
        await session.commit()
    return ids


async def test_queue_is_newest_supreme_court_first_without_editorial_text(session_factory, client: AsyncClient, strong_password: str) -> None:
    from app.modules.research.ai_headnotes import apply_ai_headnote, export_queue, pending_count

    await _user(client, "Queue LLP", "queue@firm.co", strong_password)
    ids = await _seed(session_factory)
    async with session_factory() as session:
        queue = await export_queue(session, 10)
        assert [q.id for q in queue] == [ids["new"], ids["mid"], ids["old"]]  # SC with text only, newest first
        assert queue[0].text.startswith("Case Arising From")                  # editorial headnote cut away
        assert "EDITORIAL HEADNOTE" not in queue[0].text
        assert await pending_count(session) == 3

        await apply_ai_headnote(session, ids["new"], HEADNOTE, model="claude-opus-5-5")
        await session.commit()
        assert [q.id for q in await export_queue(session, 10)] == [ids["mid"], ids["old"]]  # resumable
        assert [q.id for q in await export_queue(session, 10, skip={ids["mid"]})] == [ids["old"]]


async def test_import_validates_and_never_overwrites_silently(session_factory, client: AsyncClient, strong_password: str) -> None:
    from pydantic import ValidationError

    from app.modules.research.ai_headnotes import HeadnoteImportError, apply_ai_headnote

    await _user(client, "Import LLP", "import@firm.co", strong_password)
    ids = await _seed(session_factory)
    async with session_factory() as session:
        with pytest.raises(ValidationError):
            await apply_ai_headnote(session, ids["mid"], {**HEADNOTE, "held": []}, model="m")
        with pytest.raises(ValidationError):
            await apply_ai_headnote(session, ids["mid"], {**HEADNOTE, "extra": "x"}, model="m")
        with pytest.raises(HeadnoteImportError, match="not a Supreme Court"):
            await apply_ai_headnote(session, ids["hc"], HEADNOTE, model="m")
        with pytest.raises(HeadnoteImportError, match="not found"):
            await apply_ai_headnote(session, uuid.uuid4(), HEADNOTE, model="m")
        await apply_ai_headnote(session, ids["mid"], HEADNOTE, model="m1")
        with pytest.raises(HeadnoteImportError, match="already has"):
            await apply_ai_headnote(session, ids["mid"], HEADNOTE, model="m2")
        j = await apply_ai_headnote(session, ids["mid"], {**HEADNOTE, "result": "Appeal dismissed."}, model="m2", force=True)
        assert j.ai_headnote["result"] == "Appeal dismissed." and j.ai_headnote_model == "m2"


async def test_api_returns_headnote_flagged_as_ai_generated(session_factory, client: AsyncClient, strong_password: str) -> None:
    from app.modules.research.ai_headnotes import apply_ai_headnote

    headers, _ = await _user(client, "Flag LLP", "flag@firm.co", strong_password)
    ids = await _seed(session_factory)
    async with session_factory() as session:
        await apply_ai_headnote(session, ids["new"], HEADNOTE, model="claude-opus-5-5")
        await session.commit()

    body = (await client.get(f"{API}/research/judgments/{ids['new']}", headers=headers)).json()
    hn = body["ai_headnote"]
    assert hn["ai_generated"] is True
    assert "AI-generated" in hn["label"]
    assert hn["model"] == "claude-opus-5-5" and hn["version"] == "1" and hn["generated_at"]
    assert hn["provisions"][0]["provision"] == "Section 16(4)"
    assert body["headnote"] is None  # the Court's own text field is untouched

    other = (await client.get(f"{API}/research/judgments/{ids['old']}", headers=headers)).json()
    assert other["ai_headnote"] is None

    # Search results carry the AI summary (labelled in the UI) for headnoted judgments only.
    page = (await client.get(f"{API}/research/judgments", headers=headers, params={"court_level": "supreme_court"})).json()
    by_name = {i["case_name"]: i["ai_summary"] for i in page["items"]}
    assert by_name["new v. State"] == HEADNOTE["summary"] and by_name["old v. State"] is None


async def test_public_pages_show_only_headnoted_judgments_with_the_ai_flag(session_factory, client: AsyncClient, strong_password: str) -> None:
    from app.modules.research.ai_headnotes import apply_ai_headnote

    await _user(client, "Public LLP", "public@firm.co", strong_password)
    ids = await _seed(session_factory)
    async with session_factory() as session:
        await apply_ai_headnote(session, ids["new"], HEADNOTE, model="claude-opus-5-5")
        await apply_ai_headnote(session, ids["mid"], {**HEADNOTE, "summary": "A <b>2024</b> ruling on input tax credit."}, model="m")
        await session.commit()

    # No sign-in needed. A bare id redirects to the canonical address with the case-name slug.
    bare = await client.get(f"/judgments/{ids['new']}/", follow_redirects=False)
    assert bare.status_code == 301 and bare.headers["location"] == f"/judgments/{ids['new']}/new-v-state/"
    assert (await client.get(f"/judgments/{ids['new']}/wrong-name/", follow_redirects=False)).status_code == 301

    page = await client.get(f"/judgments/{ids['new']}/new-v-state/")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    html = page.text
    assert "AI-generated headnote" in html and "new v. State" in html and "12/08/2026" in html
    assert "Section 16(4), Central Goods and Services Tax Act, 2017" in html and "(¶¶ 12, 14)" in html
    assert f'<link rel="canonical" href="https://vidhisangh.com/judgments/{ids["new"]}/new-v-state/"' in html
    assert 'class="wa" href="https://wa.me/?text=new%20v.%20State' in html
    assert "EDITORIAL HEADNOTE" not in html and "The appeal is allowed" not in html  # no full text, no reporter text
    assert "style-src 'self'" in page.headers["content-security-policy"]

    mid = (await client.get(f"/judgments/{ids['mid']}/mid-v-state/")).text
    assert "&lt;b&gt;2024&lt;/b&gt;" in mid and "<b>2024</b>" not in mid  # escaped

    # Judgments without a headnote, High Court orders and junk ids are not pages.
    for path in (f"/judgments/{ids['old']}/", f"/judgments/{ids['hc']}/", "/judgments/not-an-id/", "/judgments/1999/"):
        assert (await client.get(path, follow_redirects=False)).status_code == 404, path

    index = (await client.get("/judgments/")).text
    assert index.index("new v. State") < index.index("mid v. State") and 'href="/judgments/2026/"' in index
    year = (await client.get("/judgments/2024/")).text
    assert "mid v. State" in year and "new v. State" not in year

    sitemap = await client.get("/sitemap-judgments.xml")
    assert sitemap.headers["content-type"].startswith("application/xml")
    assert f"https://vidhisangh.com/judgments/{ids['new']}/new-v-state/" in sitemap.text
    assert "https://vidhisangh.com/judgments/2024/" in sitemap.text and str(ids["old"]) not in sitemap.text


def test_ai_headnote_index_matches_the_query_expression() -> None:
    import importlib.util
    from pathlib import Path
    from app.modules.research.repository import AI_HEADNOTE_VECTOR_SQL
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0077_ai_headnote_search.py"
    spec = importlib.util.spec_from_file_location("m0077", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Not byte-identical → Postgres silently ignores the index (5.6M-row scan).
    assert module.AI_HEADNOTE_VECTOR_SQL == AI_HEADNOTE_VECTOR_SQL


async def test_search_finds_words_only_in_the_ai_headnote(session_factory, client: AsyncClient, strong_password: str) -> None:
    from app.modules.research.models import Judgment
    h, _ = await _user(client, "Find LLP", "find@firm.co", strong_password)
    ids = await _seed(session_factory)
    async with session_factory() as session:
        j = await session.get(Judgment, ids["mid"])
        j.ai_headnote = HEADNOTE
        await session.commit()
    hits = (await client.get(f"{API}/research/judgments", headers=h, params={"q": "procedural lapse"})).json()
    assert [r["id"] for r in hits["items"]] == [str(ids["mid"])]
