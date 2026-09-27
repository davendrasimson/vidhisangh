#!/usr/bin/env python3
"""Fetch the curated Bare Acts from the Legislative Department's official API.

The output is served as static same-origin content by the Angular application.
Run this intentionally when refreshing the statutory snapshots; the source URL,
retrieval date and selected official record are written to manifest.json.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

API = "https://www.legislative.gov.in/cms/wp-json/custom/api/search?s="
API_KEY_ENV = "VS_LEGISLATIVE_API_KEY"
HEADERS = {"User-Agent": "VidhiSangh statutory-library/1.0"}


def _headers() -> dict[str, str]:
    """Request headers with the Legislative Department API key from the
    environment. The key is a credential: it is never committed (A-12)."""
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise SystemExit(
            f"{API_KEY_ENV} is not set. Export the Legislative Department API key "
            f"in the environment (see backend/.env.example) and re-run."
        )
    return {**HEADERS, "apikey": key}
OUTPUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "bare-acts"

ACTS = {
    "bns": "Bharatiya Nyaya Sanhita 2023",
    "bnss": "Bharatiya Nagarik Suraksha Sanhita 2023",
    "bsa": "Bharatiya Sakshya Adhiniyam 2023",
    "ipc": "Indian Penal Code 1860",
    "crpc": "Code of Criminal Procedure 1973",
    "evidence": "Indian Evidence Act 1872",
    "companies": "Companies Act 2013",
    "contract": "Indian Contract Act 1872",
    "consumer": "Consumer Protection Act 2019",
    "rera": "Real Estate Regulation and Development Act 2016",
    "dv": "Protection of Women from Domestic Violence Act 2005",
    "rti": "Right to Information Act 2005",
    "cpc": "Code of Civil Procedure 1908",
    "limitation": "Limitation Act 1963",
    "arbitration": "Arbitration and Conciliation Act 1996",
    "cheque": "Negotiable Instruments Act 1881",
    "it": "Information Technology Act 2000",
    "property": "Transfer of Property Act 1882",
    "hindu-marriage": "Hindu Marriage Act 1955",
    "special-marriage": "Special Marriage Act 1954",
    "succession": "Hindu Succession Act 1956",
    "posh": "Sexual Harassment of Women at Workplace Act 2013",
    "pocso": "Protection of Children from Sexual Offences Act 2012",
    "legal-aid": "Legal Services Authorities Act 1987",
    "ibc": "Insolvency and Bankruptcy Code 2016",
}

# These records are published by official government bodies but are either not
# present in the Legislative Department search results or are outranked there
# by unrelated documents. Pinning them prevents a broad search result from
# silently replacing an Act with a circular, journal or annual report.
OFFICIAL_OVERRIDES = {
    "bns": (
        "The Bharatiya Nyaya Sanhita, 2023",
        "https://www.mha.gov.in/sites/default/files/2024-04/250883_english_01042024.pdf",
    ),
    "bnss": (
        "The Bharatiya Nagarik Suraksha Sanhita, 2023",
        "https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf",
    ),
    "bsa": (
        "The Bharatiya Sakshya Adhiniyam, 2023",
        "https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf",
    ),
    "ipc": (
        "The Indian Penal Code, 1860",
        "https://cpsurat.gujarat.gov.in/upload/008the_indian_penal_code_ghc.pdf",
    ),
    "evidence": (
        "The Indian Evidence Act, 1872",
        "https://training.delhipolice.gov.in/PDF/PublicData/EVENTS_20191127150610314.pdf",
    ),
    "companies": (
        "The Companies Act, 2013",
        "https://nclt.gov.in/sites/default/files/basicpage/the_companies_act_2013.pdf",
    ),
    "consumer": (
        "The Consumer Protection Act, 2019",
        "https://consumeraffairs.gov.in/public/upload/files/CP%20Act%202019_1732700731.pdf",
    ),
    "contract": (
        "The Indian Contract Act, 1872",
        "https://aphc.gov.in/docs/6_20241130050320.pdf",
    ),
    "rti": (
        "The Right to Information Act, 2005",
        "https://cdnbbsr.s3waas.gov.in/s3c3614206a443012045cfd75d2600af2d/uploads/2023/01/2023013137.pdf",
    ),
    "cpc": (
        "The Code of Civil Procedure, 1908",
        "https://cdnbbsr.s3waas.gov.in/s3ec03a36b598abb934e4528412e5a2127/uploads/2023/09/2023091268.pdf",
    ),
    "limitation": (
        "The Limitation Act, 1963",
        "https://cdnbbsr.s3waas.gov.in/s3ec044a11654ad1e1e48352252859ff30/uploads/2023/11/2023110196.pdf",
    ),
    "rera": (
        "The Real Estate (Regulation and Development) Act, 2016",
        "https://cdnbbsr.s3waas.gov.in/s30bf727e907c5fc9d5356f11e4c45d613/uploads/2025/09/202509122034412027.pdf",
    ),
    "arbitration": (
        "The Arbitration and Conciliation Act, 1996",
        "https://aphc.gov.in/docs/1_20250102063311.pdf",
    ),
    "ibc": (
        "The Insolvency and Bankruptcy Code, 2016",
        "https://ibbi.gov.in/uploads/legalframwork/e9cca2f4d2cf3508f3c823f070429be8.pdf",
    ),
    "it": (
        "The Information Technology Act, 2000 (as amended in 2008)",
        "https://megpolice.gov.in/sites/default/files/IT_Act_2000_2008_amendment.pdf",
    ),
    "property": (
        "The Transfer of Property Act, 1882",
        "https://www.indiacode.nic.in/bitstream/123456789/2338/1/A1882-04.pdf",
    ),
    "special-marriage": (
        "The Special Marriage Act, 1954",
        "https://spniwcd.wcd.gov.in/uploads/pdf/1714650370.pdf",
    ),
    "hindu-marriage": (
        "The Hindu Marriage Act, 1955",
        "https://www.spniwcd.wcd.gov.in/uploads/pdf/1714714662.pdf",
    ),
    "succession": (
        "The Hindu Succession Act, 1956",
        "https://www.spniwcd.wcd.gov.in/uploads/pdf/1714650808.pdf",
    ),
    "posh": (
        "The Sexual Harassment of Women at Workplace Act, 2013",
        "https://uppolice.gov.in/site/writereaddata/siteContent/acts/202202171235267454TheSexualHarassmentofWomenatWorkplacePREVENTIONPROHIBITIONandREDRESSALAct2013.pdf",
    ),
    "dv": (
        "The Protection of Women from Domestic Violence Act, 2005",
        "https://meghalaya.gov.in/meghalaya/sites/default/files/acts/Women_domestic_violence_act.pdf",
    ),
    "pocso": (
        "The Protection of Children from Sexual Offences Act, 2012",
        "https://www.wcd.gov.in/documents/uploaded/1709101314.pdf",
    ),
    "legal-aid": (
        "The Legal Services Authorities Act, 1987",
        "https://cdnbbsr.s3waas.gov.in/s32e45f93088c7db59767efef516b306aa/uploads/2025/04/202504081796627129.pdf",
    ),
}

# These readable PDFs are generated from official Delhi District Courts HTML
# publications because those pages do not provide English PDF attachments.
PRESERVE_LOCAL = {"cheque", "crpc"}


def request(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(url, headers=_headers())
            with urllib.request.urlopen(req, timeout=120) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(attempt * 2)
    raise RuntimeError(f"download failed after 4 attempts: {last_error}")


def words(value: str) -> set[str]:
    ignored = {"the", "of", "and", "act", "code"}
    return {word for word in re.findall(r"[a-z0-9]+", value.lower()) if word not in ignored}


def pdf_urls(value: object) -> list[str]:
    encoded = json.dumps(value)
    return list(dict.fromkeys(url.replace("\\/", "/") for url in re.findall(r"https[^\" ]+?\.pdf", encoded, re.I)))


def select_record(query: str, payload: dict) -> tuple[dict, str]:
    candidates: list[tuple[int, dict, str]] = []
    wanted = words(query)
    for record in payload.get("data", []):
        if record.get("type") != "central_documents":
            continue
        urls = pdf_urls(record)
        if not urls:
            continue
        title_words = words(record.get("title", ""))
        overlap = len(wanted & title_words)
        missing = len(wanted - title_words)
        score = overlap * 10 - missing * 4
        if query.split()[-1] in record.get("title", ""): score += 8
        candidates.append((score, record, urls[0]))
    if not candidates:
        raise RuntimeError("no official PDF record returned")
    _, record, url = max(candidates, key=lambda item: item[0])
    return record, url


def main() -> int:
    _headers()  # fail before any work if the API key is missing
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT / "manifest.json"
    manifest: dict[str, dict[str, str | int]] = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    failures: list[str] = []
    requested = sys.argv[1:]
    unknown = [act_id for act_id in requested if act_id not in ACTS]
    if unknown:
        print("Unknown Act ids: " + ", ".join(unknown), file=sys.stderr)
        return 2
    selected = [(act_id, ACTS[act_id]) for act_id in requested] if requested else list(ACTS.items())
    for index, (act_id, query) in enumerate(selected, 1):
        print(f"[{index:02}/{len(selected)}] {query}", flush=True)
        try:
            if act_id in PRESERVE_LOCAL:
                target = OUTPUT / f"{act_id}.pdf"
                if not target.exists() or not target.read_bytes().startswith(b"%PDF-"):
                    raise RuntimeError("maintained local reading copy is missing or invalid")
                print(f"     preserved local official-page snapshot ({target.stat().st_size / 1024:.0f} KB)", flush=True)
                continue
            if act_id in OFFICIAL_OVERRIDES:
                title, source = OFFICIAL_OVERRIDES[act_id]
            else:
                payload = json.loads(request(API + urllib.parse.quote(query)))
                record, source = select_record(query, payload)
                title = record.get("title", query)
            content = request(source)
            if not content.startswith(b"%PDF-"):
                raise RuntimeError("official attachment is not a PDF")
            target = OUTPUT / f"{act_id}.pdf"
            target.write_bytes(content)
            manifest[act_id] = {
                "title": title,
                "official_source": source,
                "retrieved_on": date.today().isoformat(),
                "bytes": len(content),
            }
            print(f"     {len(content) / 1024:.0f} KB", flush=True)
        except Exception as exc:  # keep a partial refresh inspectable
            failures.append(act_id)
            print(f"     FAILED: {exc}", file=sys.stderr, flush=True)
        time.sleep(0.15)

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Library contains {len(manifest)} of {len(ACTS)} Acts in {OUTPUT}")
    if failures:
        print("Missing: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
