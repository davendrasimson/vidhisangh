"""Cite check — citation parsing and resolution against the corpus (no LLM)."""

from __future__ import annotations

import uuid
from datetime import date
from io import BytesIO

import pytest
from docx import Document
from httpx import AsyncClient
from sqlalchemy import select

from app.modules.research.cite_check import find_citations, party_tokens
from tests.test_research import API, _user

pytestmark = pytest.mark.asyncio

DRAFT = """
1. The right to privacy is a fundamental right: K.S. Puttaswamy v. Union of India, (2017) 10 SCC 1.
2. In Delhi Transport Corporation v. Balwan Singh & Ors., [2019] 4 SCR 532 the Court held that
   a daily wager is not a workman. The same case is reported as 2019 INSC 267.
3. See also the Allahabad High Court in Ram Lal v. State of U.P., 2023:AHC:174410.
4. Reliance is placed on Foo Industries v. Bar Traders, (2031) 9 SCC 999 and on AIR 2019 SC 1234.
5. Puttaswamy (supra), 2017 (10) SCC 1, was followed in Anuradha Bhasin v. Union of India, (2020) 3 SCC 637.
"""


async def test_find_citations_normalises_and_groups() -> None:
    found = {c.normalised: c for c in find_citations(DRAFT)}
    assert "(2017) 10 SCC 1" in found and found["(2017) 10 SCC 1"].occurrences.__len__() == 2  # both spellings
    assert found["(2017) 10 SCC 1"].case_names[0] == "K.S. Puttaswamy v. Union of India"
    assert found["[2019] 4 S.C.R. 532"].kind == "scr"
    assert found["[2019] 4 S.C.R. 532"].case_names == ["Delhi Transport Corporation v. Balwan Singh & Ors."]
    assert found["2019 INSC 267"].kind == "insc"
    assert found["2023:AHC:174410"].kind == "neutral"
    assert found["2023:AHC:174410"].case_names == ["Ram Lal v. State of U.P."]
    assert found["(2031) 9 SCC 999"].case_names == ["Foo Industries v. Bar Traders"]
    assert found["AIR 2019 SC 1234"].reporter == "AIR"
    assert found["(2020) 3 SCC 637"].case_names == ["Anuradha Bhasin v. Union of India"]
    # Reading order, one entry per distinct citation.
    assert [c.normalised for c in find_citations(DRAFT)][:3] == ["(2017) 10 SCC 1", "[2019] 4 S.C.R. 532", "2019 INSC 267"]


async def test_more_reporter_forms() -> None:
    text = ("(2019) 5 SCC (Cri) 12; 1996 Supp (1) SCC 1; 2019 SCC OnLine Del 1234; 2019 (5) SCALE 100; "
            "JT 2019 (5) SC 7; 2019 Cri LJ 456; AIR 2018 Del 12; [1996] SUPP. 1 S.C.R. 499; 2023:AHC-LKO:1234-DB")
    got = [c.normalised for c in find_citations(text)]
    assert got == [
        "(2019) 5 SCC (Cri) 12", "1996 Supp (1) SCC 1", "2019 SCC OnLine Del 1234", "2019 (5) SCALE 100",
        "JT 2019 (5) SC 7", "2019 Cri LJ 456", "AIR 2018 Del 12", "[1996] SUPP. 1 S.C.R. 499", "2023:AHC-LKO:1234-DB",
    ]


async def test_party_tokens_skip_generic_words() -> None:
    assert party_tokens("K.S. Puttaswamy v. Union of India") == ["puttaswamy"]
    assert party_tokens("State of Haryana v. Chandvir and Ors.") == ["haryana", "chandvir"]
    assert party_tokens("Delhi Transport Corporation v. Balwan Singh & Ors.") == ["transport", "balwan", "singh"]


async def _seed(session_factory) -> dict[str, uuid.UUID]:
    from app.modules.identity.models import User
    from app.modules.research.models import CourtLevel, Judgment

    ids: dict[str, uuid.UUID] = {}
    async with session_factory() as session:
        user_id = (await session.execute(select(User.id).limit(1))).scalar_one()
        rows = [
            ("dtc", "DELHI TRANSPORT CORPORATION versus BALWAN SINGH & ORS.", "[2019] 4 S.C.R. 532", "2019 INSC 267",
             CourtLevel.SUPREME_COURT, "Supreme Court of India", date(2019, 2, 26),
             "Civil appeal. The respondent was engaged as a daily wager."),
            ("puttaswamy", "JUSTICE K.S. PUTTASWAMY (RETD.) versus UNION OF INDIA", "[2017] 10 S.C.R. 569", "2017 INSC 801",
             CourtLevel.SUPREME_COURT, "Supreme Court of India", date(2017, 8, 24),
             "Privacy is intrinsic to life and liberty."),
            ("bhasin", "ANURADHA BHASIN versus UNION OF INDIA", "[2020] 1 S.C.R. 1", "2020 INSC 20",
             CourtLevel.SUPREME_COURT, "Supreme Court of India", date(2020, 1, 10),
             "In K.S. Puttaswamy v. Union of India, (2017) 10 SCC 1 this Court held that privacy is a fundamental right. "
             "AIR 2019 SC 1234 was distinguished."),
            ("hc", "WRIT - A No. 1 of 2023 of Ram Lal Vs State of U.P.", None, "2023:AHC:174410",
             CourtLevel.HIGH_COURT, "Allahabad High Court", date(2023, 9, 1), "Order of the High Court."),
        ]
        for key, name, cit, neutral, level, court, day, text in rows:
            j = Judgment(case_name=name, cause_title=name, citation=cit, neutral_citation=neutral, court=court,
                         court_level=level, judgment_date=day, full_text=text, added_by=user_id)
            session.add(j)
            await session.flush()
            ids[key] = j.id
        await session.commit()
    return ids


async def test_cite_check_report(session_factory, client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Cite LLP", "cite@firm.co", strong_password)
    ids = await _seed(session_factory)

    resp = await client.post(f"{API}/research/cite-check", headers=h, json={"text": DRAFT})
    assert resp.status_code == 200, resp.text
    report = resp.json()
    by = {f["citation"]: f for f in report["findings"]}

    assert report["citations_found"] == 8 and report["distinct_citations"] == 7 and not report["truncated"]

    scr = by["[2019] 4 S.C.R. 532"]
    assert scr["status"] == "verified" and scr["judgment"]["id"] == str(ids["dtc"]) and scr["warnings"] == []
    assert by["2019 INSC 267"]["status"] == "verified" and by["2019 INSC 267"]["judgment"]["id"] == str(ids["dtc"])
    assert by["2023:AHC:174410"]["status"] == "verified" and by["2023:AHC:174410"]["judgment"]["id"] == str(ids["hc"])

    # SCC is not a key the library holds: resolved by the parties' names and year, and the
    # citing judgment is reported too.
    putt = by["(2017) 10 SCC 1"]
    assert putt["status"] == "matched_by_name" and putt["judgment"]["id"] == str(ids["puttaswamy"])
    assert putt["occurrences"] == 2 and putt["cited_in_count"] == 0   # resolved, so the costly citing-text search is skipped
    assert any("keys this case as [2017] 10 S.C.R. 569" in w for w in putt["warnings"])
    assert by["(2020) 3 SCC 637"]["status"] == "matched_by_name"

    # Only cited by another judgment — exists, but no record of its own.
    air = by["AIR 2019 SC 1234"]
    assert air["status"] == "cited_elsewhere" and air["cited_in_count"] == 1 and air["judgment"] is None
    assert air["cited_in_examples"][0]["id"] == str(ids["bhasin"])

    # A citation nothing in the library knows: flagged for manual verification.
    fake = by["(2031) 9 SCC 999"]
    assert fake["status"] == "not_found" and fake["case_name_as_cited"] == "Foo Industries v. Bar Traders"
    assert any("verify this citation" in w for w in fake["warnings"])

    assert report["counts"] == {"verified": 3, "matched_by_name": 2, "cited_elsewhere": 1, "not_found": 1}
    assert "first pass" in report["note"]


async def test_cite_check_year_mismatch_warning(session_factory, client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Year LLP", "year@firm.co", strong_password)
    await _seed(session_factory)
    resp = await client.post(f"{API}/research/cite-check", headers=h,
                             json={"text": "Wrongly dated: Some Other Case v. Nobody, 2019 INSC 267."})
    f = resp.json()["findings"][0]
    assert f["status"] == "verified"
    assert any("does not contain the names cited" in w for w in f["warnings"])


async def test_cite_check_docx_upload_reads_footnotes(session_factory, client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Docx LLP", "docx@firm.co", strong_password)
    ids = await _seed(session_factory)
    doc = Document()
    doc.add_paragraph("The petitioner relies on Delhi Transport Corporation v. Balwan Singh, [2019] 4 SCR 532.")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Authority"
    table.cell(0, 1).text = "2023:AHC:174410"
    buf = BytesIO()
    doc.save(buf)
    files = {"file": ("draft.docx", buf.getvalue(),
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    resp = await client.post(f"{API}/research/cite-check/upload", headers=h, files=files)
    assert resp.status_code == 200, resp.text
    by = {f["citation"]: f for f in resp.json()["findings"]}
    assert by["[2019] 4 S.C.R. 532"]["judgment"]["id"] == str(ids["dtc"])
    assert by["2023:AHC:174410"]["status"] == "verified"

    bad = await client.post(f"{API}/research/cite-check/upload", headers=h,
                            files={"file": ("x.txt", b"plain text", "text/plain")})
    assert bad.status_code == 415


async def test_cite_check_requires_research_permission(client: AsyncClient, strong_password: str) -> None:
    resp = await client.post(f"{API}/research/cite-check", json={"text": "(2017) 10 SCC 1"})
    assert resp.status_code == 401
