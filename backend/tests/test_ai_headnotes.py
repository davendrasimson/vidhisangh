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
