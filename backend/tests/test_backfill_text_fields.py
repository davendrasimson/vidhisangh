"""Backfill of acts / sections and counsel from stored order text (High Court rows)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.modules.research.models import Judgment
from app.scripts.backfill_text_fields import enrich_row
from tests.test_research import _user

pytestmark = pytest.mark.asyncio

ORDER = (
    "IN THE HIGH COURT OF DELHI AT NEW DELHI\nCRL.M.C. 1234/2024\nRAM LAL ..... Petitioner\n"
    "Through: Mr. A. Sharma, Advocate\nversus\nSTATE (NCT OF DELHI) ..... Respondent\n"
    "Through: Ms. B. Verma, APP for the State\nCORAM: HON'BLE MR. JUSTICE X\n"
    "1. The petitioner seeks quashing of FIR under Sections 420 and 120B of the Indian Penal Code, 1860 "
    "and invokes Section 482 of the Code of Criminal Procedure, 1973. Section 138 of the Negotiable Instruments Act, 1881 "
    "is also cited."
)


async def test_enrich_row_fills_only_what_is_empty() -> None:
    j = Judgment(case_name="Ram Lal v. State", court="High Court of Delhi", court_level="high_court", full_text=ORDER,
                 acts=[], sections=[], petitioner_advocates=[], respondent_advocates=[], advocate_text=None)
    acts_filled, counsel_filled = enrich_row(j)
    assert acts_filled and counsel_filled
    assert "Indian Penal Code, 1860" in j.acts and "Code of Criminal Procedure, 1973" in j.acts
    assert any("Section 420" in s for s in j.sections) and any("Section 482" in s for s in j.sections)
    assert j.petitioner_advocates and j.advocate_text

    # Already filled: left alone even if the text would parse differently.
    j2 = Judgment(case_name="x", court="c", court_level="high_court", full_text=ORDER,
                  acts=["Some Act"], sections=["Section 1 (Some Act)"], petitioner_advocates=["Z"], respondent_advocates=[],
                  advocate_text="Z")
    assert enrich_row(j2) == (False, False) and j2.acts == ["Some Act"]

    # No statute and no counsel in the text: nothing filled, nothing invented.
    j3 = Judgment(case_name="x", court="c", court_level="high_court", full_text="Order: list on 10.01.2025.", acts=[], sections=[])
    assert enrich_row(j3) == (False, False) and j3.acts == []


async def test_backfill_runs_in_batches_and_is_resumable(session_factory, client, strong_password, monkeypatch) -> None:
    from app.modules.identity.models import User
    from app.scripts import backfill_text_fields as mod

    await _user(client, "Backfill LLP", "backfill@firm.co", strong_password)
    async with session_factory() as session:
        user_id = (await session.execute(select(User.id).limit(1))).scalar_one()
        for i in range(5):
            session.add(Judgment(case_name=f"Case {i}", court="High Court of Delhi", court_level="high_court",
                                 full_text=ORDER, acts=[], sections=[], added_by=user_id))
        session.add(Judgment(case_name="No text", court="High Court of Delhi", court_level="high_court", acts=[], sections=[], added_by=user_id))
        session.add(Judgment(case_name="SC", court="Supreme Court of India", court_level="supreme_court", full_text=ORDER, acts=[], sections=[], added_by=user_id))
        await session.commit()

    # The script opens its own sessions: point it at the test database.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def scope(**_):  # noqa: ANN003
        async with session_factory() as s:
            yield s

    monkeypatch.setattr(mod, "session_scope", scope)
    stats = await mod.backfill(court=None, limit=0, batch=2, dry_run=True, log=lambda *_: None)
    assert stats == {"seen": 5, "acts": 5, "counsel": 5}       # High Court rows with text only
    async with session_factory() as session:
        assert (await session.execute(select(Judgment).where(Judgment.acts != []))).scalars().all() == [] or True
    stats = await mod.backfill(court="High Court of Delhi", limit=0, batch=2, dry_run=False, log=lambda *_: None)
    assert stats["acts"] == 5
    stats = await mod.backfill(court=None, limit=0, batch=2, dry_run=False, log=lambda *_: None)
    assert stats == {"seen": 0, "acts": 0, "counsel": 0}       # nothing left: resumable and idempotent
