"""Statutory references in the cite check: IPC / CrPC / Evidence → BNS / BNSS / BSA."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.modules.research.statutes import find_statute_references, tables
from tests.test_research import API, _user

pytestmark = pytest.mark.asyncio

DRAFT = """
The accused is charged under Sections 420, 406 and 120B IPC and u/s 376(2)(n) of the Indian Penal Code.
Anticipatory bail was sought under Section 438 Cr.P.C.; the FIR was registered under Section 154 of the Code of
Criminal Procedure, 1973. The WhatsApp chats need a certificate under Section 65B of the Indian Evidence Act, 1872.
Sedition under Section 124A IPC is no longer on the statute book. Section 999 IPC is a typo.
For the new case, the charge is under Section 318(4) of the Bharatiya Nyaya Sanhita, 2023 and bail under Section 482 BNSS.
"""


async def test_backend_tables_match_the_frontend_copies() -> None:
    root = Path(__file__).resolve().parents[2]
    for act in ("bns", "bnss", "bsa"):
        backend = (root / "backend/app/modules/research/correspondence" / f"{act}.json").read_text(encoding="utf-8")
        frontend = (root / "frontend/content/correspondence" / f"{act}.json").read_text(encoding="utf-8")
        assert json.loads(backend) == json.loads(frontend), f"{act}.json differs: copy frontend/content/correspondence/{act}.json over the backend copy"
    assert tables()["bns"].old_to_new["420"] == [("318(4)", "Cheating and dishonestly inducing delivery of property")]


async def test_find_statute_references_maps_old_to_new() -> None:
    by = {(s.act, s.base): s for s in find_statute_references(DRAFT)}
    assert by[("ipc", "420")].status == "mapped" and by[("ipc", "420")].new_sections == ["318(4)"]
    assert by[("ipc", "420")].converter_path == "/acts/ipc-to-bns/section-420/"
    assert by[("ipc", "406")].new_sections == ["316(2)"]
    assert by[("ipc", "120B")].new_sections == ["61"] or by[("ipc", "120B")].status == "mapped"
    sec376 = by[("ipc", "376")]
    assert sec376.section == "376(2)(n)" and sec376.status == "mapped" and sec376.new_sections   # 64 …
    assert by[("crpc", "438")].new_sections == ["482"] and by[("crpc", "438")].new_act_label == "BNSS"
    assert by[("crpc", "154")].new_sections == ["173"]
    assert by[("evidence", "65B")].status == "mapped" and by[("evidence", "65B")].new_act == "bsa"
    assert by[("ipc", "124A")].status == "not_carried" and "no corresponding provision" in by[("ipc", "124A")].note
    assert by[("ipc", "999")].status == "unknown"
    bns = by[("bns", "318")]
    assert bns.status == "new_law" and bns.section == "318(4)" and bns.old_sections == ["420"]
    assert by[("bnss", "482")].status == "new_law" and by[("bnss", "482")].old_sections == ["438"]
    assert by[("ipc", "420")].occurrences == 1


async def test_report_carries_statutes(client: AsyncClient, strong_password: str) -> None:
    h, _ = await _user(client, "Statute LLP", "statute@firm.co", strong_password)
    resp = await client.post(f"{API}/research/cite-check", headers=h, json={"text": DRAFT})
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["statute_counts"]["mapped"] >= 6 and report["statute_counts"]["not_carried"] == 1 and report["statute_counts"]["unknown"] == 1
    s420 = next(s for s in report["statutes"] if s["act"] == "ipc" and s["base"] == "420")
    assert s420["subject"] == "Cheating and dishonestly inducing delivery of property" and "BNS 318(4)" in s420["note"]
