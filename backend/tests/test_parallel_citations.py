"""Parallel citations (migration 0080): mined from judgment texts, used by the cite check."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.modules.research.parallel_citations import mine
from tests.test_research import API, _user

pytestmark = pytest.mark.asyncio


async def _seed(session_factory) -> dict[str, uuid.UUID]:
    from app.modules.identity.models import User
    from app.modules.research.models import CourtLevel, Judgment

    ids: dict[str, uuid.UUID] = {}
    async with session_factory() as session:
        user_id = (await session.execute(select(User.id).limit(1))).scalar_one()
        rows = [
            ("puttaswamy", "JUSTICE K.S. PUTTASWAMY (RETD.) versus UNION OF INDIA", "[2017] 10 S.C.R. 569", "2017 INSC 801",
             date(2017, 8, 24), "Privacy is intrinsic to life and liberty."),
            ("maneka", "MANEKA GANDHI versus UNION OF INDIA", "[1978] 2 S.C.R. 621", "1978 INSC 16",
             date(1978, 1, 25), "The procedure must be fair, just and reasonable."),
            # Two later judgments cite Puttaswamy by its SCC citation; one cites Maneka by AIR.
            ("bhasin", "ANURADHA BHASIN versus UNION OF INDIA", "[2020] 1 S.C.R. 1", "2020 INSC 20", date(2020, 1, 10),
             "In K.S. Puttaswamy v. Union of India, (2017) 10 SCC 1 this Court held that privacy is a fundamental right. "
             "Maneka Gandhi v. Union of India, AIR 1978 SC 597 settled the procedure. Some Delhi case, 2019 SCC OnLine Del 1234, is not ours."),
            ("navtej", "NAVTEJ SINGH JOHAR versus UNION OF INDIA", "[2018] 7 S.C.R. 379", "2018 INSC 790", date(2018, 9, 6),
             "Following Puttaswamy v. Union of India, (2017) 10 SCC 1, dignity includes sexual autonomy. "
             "An unknown authority is Foo v. Bar, (2016) 9 SCC 999."),
        ]
        for key, name, cit, neutral, day, text in rows:
            j = Judgment(case_name=name, cause_title=name, citation=cit, neutral_citation=neutral, court="Supreme Court of India",
                         court_level=CourtLevel.SUPREME_COURT, judgment_date=day, full_text=text, added_by=user_id)
            session.add(j)
            await session.flush()
            ids[key] = j.id
        await session.commit()
    return ids


async def test_mining_resolves_named_citations_and_counts_support(session_factory, client: AsyncClient, strong_password: str) -> None:
    from app.modules.research.models import JudgmentAlias

    await _user(client, "Alias LLP", "alias@firm.co", strong_password)
    ids = await _seed(session_factory)
    async with session_factory() as session:
        stats = await mine(session, log=lambda *_: None)
        await session.commit()
    assert stats["judgments"] == 4 and stats["resolved"] == 2 and stats["added"] == 2
    assert stats["unresolved"] == 1          # Foo v. Bar: no record; SCC OnLine Del was never mineable
    async with session_factory() as session:
        aliases = {a.citation: a for a in (await session.execute(select(JudgmentAlias))).scalars().all()}
    putt = aliases["(2017) 10 SCC 1"]
    assert putt.judgment_id == ids["puttaswamy"] and putt.support == 2 and putt.reporter == "SCC"
    assert putt.case_name_as_cited in {"K.S. Puttaswamy v. Union of India", "Puttaswamy v. Union of India"}
    maneka = aliases["AIR 1978 SC 597"]
    assert maneka.judgment_id == ids["maneka"] and maneka.support == 1

    # Re-running changes nothing (idempotent), and a curated row is never overwritten.
    async with session_factory() as session:
        row = (await session.execute(select(JudgmentAlias).where(JudgmentAlias.citation == "AIR 1978 SC 597"))).scalar_one()
        row.source, row.judgment_id = "curated", ids["puttaswamy"]
        await session.commit()
    async with session_factory() as session:
        stats = await mine(session, log=lambda *_: None)
        await session.commit()
        assert (stats["added"], stats["updated"]) == (0, 0)
        row = (await session.execute(select(JudgmentAlias).where(JudgmentAlias.citation == "AIR 1978 SC 597"))).scalar_one()
        assert row.judgment_id == ids["puttaswamy"] and row.source == "curated"


async def test_cite_check_and_detail_use_aliases(session_factory, client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Alias2 LLP", "alias2@firm.co", strong_password)
    ids = await _seed(session_factory)
    async with session_factory() as session:
        await mine(session, log=lambda *_: None)
        await session.commit()

    # No case name in the draft at all — only the alias can resolve it, and it does, exactly.
    resp = await client.post(f"{API}/research/cite-check", headers=h, json={"text": "See (2017) 10 SCC 1 at para 3 and AIR 1978 SC 597."})
    by = {f["citation"]: f for f in resp.json()["findings"]}
    assert by["(2017) 10 SCC 1"]["status"] == "verified" and by["(2017) 10 SCC 1"]["judgment"]["id"] == str(ids["puttaswamy"])
    assert any("2 citing judgments name this case" in w for w in by["(2017) 10 SCC 1"]["warnings"])
    assert by["AIR 1978 SC 597"]["status"] == "verified" and by["AIR 1978 SC 597"]["judgment"]["id"] == str(ids["maneka"])

    detail = (await client.get(f"{API}/research/judgments/{ids['puttaswamy']}", headers=h)).json()
    assert detail["aliases"] == ["(2017) 10 SCC 1"]
