"""Ingest High Court order records from the AWS Open Data mirror of eCourts.

Source: the ``indian-high-court-judgments`` public S3 bucket (ap-south-1),
CC-BY-4.0, readable without an AWS account — a plain HTTPS GET, no scraping.

    https://registry.opendata.aws/indian-high-court-judgments/

Laid out as ``metadata/parquet/year=YYYY/court=<code>/bench=<code>/metadata.parquet``.

Run:  python -m app.scripts.ingest_hc_judgments --courts phhc,delhi,allahabad
      python -m app.scripts.ingest_hc_judgments --courts delhi --year-from 2024
      python -m app.scripts.ingest_hc_judgments --list-courts
      python -m app.scripts.ingest_hc_judgments --courts phhc --dry-run

How this differs from `ingest_scr_judgments`
--------------------------------------------
* **No citations.** These are order records, not law-report entries, so
  ``citation`` is left NULL and rows are keyed by ``source_ref``
  (``<court>:<cnr>:<date>``) with ``ON CONFLICT DO NOTHING``. That is what makes
  a re-run idempotent without holding millions of keys in memory.
* **Streaming.** At ~5.7M rows for three courts, the Supreme Court script's
  "load everything into a list, then dedupe" approach would exhaust memory. This
  one walks one parquet file at a time and inserts in batches.
* **No enrichment.** Fetching millions of order PDFs is not practical, so
  ``headnote``/``acts``/``sections`` stay empty. The provider's ``description``
  is kept as a searchable snippet instead.

Data quality varies by court: Punjab & Haryana populates ``disposal_nature``,
Delhi leaves it blank. Nothing is invented to paper over that.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import re
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql import insert as core_insert

import app.db.base  # noqa: F401 — register models
from app.core.database import session_scope
from app.modules.identity.models import User
from app.modules.research.models import CourtLevel, Judgment
from app.modules.research.normalise import (
    advocate_text,
    normalise_judges,
    parse_counsel,
    parse_neutral_citation,
    parse_registry_title,
    split_parties,
)

log = structlog.get_logger("app.ingest_hc")

BUCKET = "https://indian-high-court-judgments.s3.ap-south-1.amazonaws.com"
PREFIX = "metadata/parquet/"

# Friendly name -> the bucket's court partition code.
COURTS: dict[str, tuple[str, str]] = {
    "phhc": ("3_22", "Punjab & Haryana High Court"),
    "delhi": ("7_26", "Delhi High Court"),
    "allahabad": ("9_13", "Allahabad High Court"),
    "bombay": ("27_1", "Bombay High Court"),
    "calcutta": ("19_16", "Calcutta High Court"),
    "madras": ("33_10", "Madras High Court"),
    "karnataka": ("29_3", "Karnataka High Court"),
    "kerala": ("32_4", "Kerala High Court"),
    "gujarat": ("24_17", "Gujarat High Court"),
    "mp": ("23_23", "Madhya Pradesh High Court"),
    "rajasthan": ("8_9", "Rajasthan High Court"),
    "patna": ("10_8", "Patna High Court"),
    "ap": ("28_2", "Andhra Pradesh High Court"),
    "telangana": ("36_29", "Telangana High Court"),
    "jk": ("1_12", "High Court of J&K and Ladakh"),
    "chhattisgarh": ("22_18", "Chhattisgarh High Court"),
    "jharkhand": ("20_7", "Jharkhand High Court"),
    "uttarakhand": ("5_15", "Uttarakhand High Court"),
    "gauhati": ("18_6", "Gauhati High Court"),
    "himachal": ("2_5", "Himachal Pradesh High Court"),
    "manipur": ("14_25", "Manipur High Court"),
    "meghalaya": ("17_21", "Meghalaya High Court"),
    "sikkim": ("11_24", "Sikkim High Court"),
    "tripura": ("16_20", "Tripura High Court"),
    "orissa": ("21_11", "Orissa High Court"),
}

_BATCH = 5_000


def _list_keys() -> list[str]:
    """Every parquet key in the bucket (one listing, then filtered locally)."""
    keys: list[str] = []
    token: str | None = None
    while True:
        url = f"{BUCKET}/?list-type=2&prefix={urllib.parse.quote(PREFIX)}&max-keys=1000"
        if token:
            url += "&continuation-token=" + urllib.parse.quote(token, safe="")
        body = urllib.request.urlopen(url, timeout=120).read().decode()
        keys += re.findall(r"<Key>(.*?)</Key>", body)
        match = re.search(r"<NextContinuationToken>(.*?)</NextContinuationToken>", body)
        if not match:
            break
        token = match.group(1)
    return keys


def _parse_registration(value) -> date | None:  # noqa: ANN001
    """Registries print the filing date as `16-05-2023`; tolerate ISO and slashes."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()[:10]
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return _parse_date(value)


def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _clean(value, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text[:limit] or None


# Registry bench codes (the bucket's `bench=` partition) -> where the bench sits.
BENCH_NAMES: dict[str, str] = {
    "phhc": "Chandigarh",
    "dhcdb": "New Delhi",
    "cisdb_16012018": "Allahabad",
    "cishclko": "Lucknow",
    "ukhcucis_pg": "Nainital",
}


def order_pdf_url(court_code: str, bench_code: str, decided: date | None, pdf_link: str | None) -> str | None:
    """Where the bucket really keeps an order PDF.

    The metadata's `pdf_link` (`court/cnrorders/<bench>/orders/<file>` or a
    bare `orders_<year>_<n>.pdf`) is the registry's own path and does not exist
    in the bucket; the PDFs are partitioned like the metadata,
    `data/pdf/year=<decision year>/court=<code>/bench=<code>/<file>`. The first
    5.6M rows were loaded with the registry path and every link 404'd.
    """
    if not pdf_link or decided is None:
        return None
    filename = pdf_link.rsplit("/", 1)[-1]
    return f"{BUCKET}/data/pdf/year={decided.year}/court={court_code}/bench={bench_code}/{filename}"


def _row(
    rec: dict, court_name: str, court_code: str, bench_code: str, added_by: uuid.UUID
) -> dict | None:
    title = _clean(rec.get("title"), 500)
    cnr = _clean(rec.get("cnr"), 20)
    decided = _parse_date(rec.get("decision_date"))
    if not title or not cnr:
        return None

    judge = _clean(rec.get("judge"), 300)
    url = order_pdf_url(court_code, bench_code, decided, rec.get("pdf_link"))
    description = _clean(rec.get("description"), 2000)
    # Same derivations the backfills apply, so newly loaded rows carry parties,
    # counsel, filing date and neutral citation from the start (migration 0039).
    registry = parse_registry_title(title, decided)
    petitioner, respondent = split_parties(registry.cause_title)
    pet_adv, resp_adv = parse_counsel(description)

    return {
        "id": uuid.uuid4(),
        "case_name": title,
        "citation": None,                       # order records carry none
        "neutral_citation": parse_neutral_citation(description),
        "cnr_number": cnr,
        # Structured fields (0036) written directly, so a newly loaded court
        # needs no separate `backfill_case_fields` pass before it facets.
        "case_type": registry.case_type,
        "case_number": registry.case_number,
        "case_year": registry.case_year,
        "cause_title": registry.cause_title,
        "judge_text": normalise_judges([judge] if judge else []),
        "filed_on": _parse_registration(rec.get("date_of_registration")),
        "petitioner": petitioner,
        "respondent": respondent,
        "petitioner_advocates": pet_adv,
        "respondent_advocates": resp_adv,
        "advocate_text": advocate_text(pet_adv, resp_adv),
        "source_ref": f"{court_code}:{cnr}:{decided or 'na'}"[:120],
        "court": _clean(rec.get("court"), 200) or court_name,
        "court_level": CourtLevel.HIGH_COURT.value,
        "bench": BENCH_NAMES.get(bench_code, bench_code),
        "judges": [judge] if judge else [],
        "judgment_date": decided,
        "acts": [],
        "sections": [],
        "keywords": [],
        # Not a headnote — the registry's own one-line description, kept so
        # these rows are searchable at all. Never presented as the Court's holding.
        "headnote": _clean(rec.get("description"), 2000),
        "outcome": _clean(rec.get("disposal_nature"), 300),
        "url": _clean(url, 500),
        "added_by": added_by,
    }


async def _flush(session, rows: list[dict]) -> int:
    """Insert a batch, skipping anything already present."""
    if not rows:
        return 0
    table = Judgment.__table__
    if session.bind.dialect.name == "postgresql":
        stmt = pg_insert(table).on_conflict_do_nothing(index_elements=["source_ref"])
    else:
        stmt = core_insert(table).prefix_with("OR IGNORE")
    await session.execute(stmt, rows)
    await session.commit()
    return len(rows)


async def ingest(
    courts: list[str], year_from: int, year_to: int, dry_run: bool, limit: int
) -> None:
    import pyarrow.parquet as pq  # lazy — only ingestion needs it

    wanted = {}
    for name in courts:
        if name not in COURTS:
            raise SystemExit(f"Unknown court '{name}'. Try --list-courts.")
        code, label = COURTS[name]
        wanted[code] = label

    keys = _list_keys()
    selected = []
    for key in keys:
        cm = re.search(r"court=([^/]+)/", key)
        ym = re.search(r"year=(\d{4})", key)
        bm = re.search(r"bench=([^/]+)/", key)
        if not cm or not ym or not bm:
            continue
        if cm.group(1) in wanted and year_from <= int(ym.group(1)) <= year_to:
            selected.append((int(ym.group(1)), cm.group(1), bm.group(1), key))
    selected.sort(reverse=True)  # newest first — most useful data lands soonest
    log.info("files_selected", files=len(selected), courts=list(wanted.values()))

    async with session_scope(bypass_rls=True) as session:
        added_by = (await session.execute(select(User.id).limit(1))).scalar_one()

        total = skipped = 0
        for year, code, bench_code, key in selected:
            label = wanted[code]
            raw = urllib.request.urlopen(
                f"{BUCKET}/{urllib.parse.quote(key)}", timeout=900
            ).read()
            parquet = pq.ParquetFile(io.BytesIO(raw))

            file_rows = 0
            batch: list[dict] = []
            for chunk in parquet.iter_batches(batch_size=_BATCH):
                for rec in chunk.to_pylist():
                    row = _row(rec, label, code, bench_code, added_by)
                    if row is None:
                        skipped += 1
                        continue
                    batch.append(row)
                    if len(batch) >= _BATCH:
                        if not dry_run:
                            await _flush(session, batch)
                        file_rows += len(batch)
                        batch = []
                if limit and total + file_rows >= limit:
                    break
            if batch:
                if not dry_run:
                    await _flush(session, batch)
                file_rows += len(batch)

            total += file_rows
            log.info("file_done", year=year, court=label, rows=file_rows, total=total)
            if limit and total >= limit:
                log.info("limit_reached", limit=limit)
                break

        log.info("ingest_complete", rows=total, unusable=skipped, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest High Court order records (AWS Open Data, CC-BY-4.0)."
    )
    parser.add_argument("--courts", default="phhc,delhi,allahabad",
                        help="Comma-separated keys; see --list-courts.")
    parser.add_argument("--year-from", type=int, default=1950)
    parser.add_argument("--year-to", type=int, default=2026)
    parser.add_argument(
        "--limit", type=int, default=0,
        help=f"Stop after roughly N rows (0 = all). Checked at batch boundaries, "
             f"so it overshoots by up to {_BATCH}.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-courts", action="store_true")
    args = parser.parse_args()

    if args.list_courts:
        for key, (code, label) in sorted(COURTS.items(), key=lambda kv: kv[1][1]):
            print(f"  {key:14} {code:7} {label}")
        return
    asyncio.run(ingest(
        [c.strip() for c in args.courts.split(",") if c.strip()],
        args.year_from, args.year_to, args.dry_run, args.limit,
    ))


if __name__ == "__main__":  # pragma: no cover
    main()
