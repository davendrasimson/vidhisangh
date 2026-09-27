"""Ingest **real** Supreme Court judgments from the AWS Open Data mirror.

Source: the ``indian-supreme-court-judgments`` public S3 bucket (ap-south-1),
a mirror of the Supreme Court's own SCR/eSCR reports covering 1950–2026.
Licensed **CC-BY-4.0**, readable without an AWS account, so this is a plain
HTTPS GET — no scraping, no CAPTCHA, no terms-of-service grey area.

    https://registry.opendata.aws/indian-supreme-court-judgments/

Run:  python -m app.scripts.ingest_scr_judgments                  # 100 from 2025
      python -m app.scripts.ingest_scr_judgments --year 2024 --count 250
      python -m app.scripts.ingest_scr_judgments --year-from 2010 --year-to 2026 \
          --count 0 --purge-sample        # replace the fake corpus with the real one
      python -m app.scripts.ingest_scr_judgments --dry-run        # print, don't write
      python -m app.scripts.ingest_scr_judgments --clear          # remove ingested rows

``--count N`` means "the first N judgments of that year", not "N more" — so
re-running is a no-op rather than pulling the next N. Raise ``--count`` or
change ``--year`` to add more.

Why some fields stay empty
--------------------------
``headnote``, ``acts``, ``sections``, ``keywords`` and ``bench`` are **not**
reliably in the source and are deliberately left blank rather than invented — a
wrong headnote or bench on a real citation is worse than none. They are also the fields with legal exposure:
s.52(1)(q)(iv) of the Copyright Act puts the *judgment text* in the public
domain, but *Eastern Book Company v. D.B. Modak* (2008) held that publishers'
headnotes and editorial notes are protected. So these must be generated from
the judgment text by our own summarisation pipeline, never copied from SCC,
Manupatra or similar.

Attribution (CC-BY) is carried by the stored ``url``, which points at the
source PDF in the open bucket.

Real rows are distinguished from the generated ones in `seed_sample_corpus.py`
by that URL host, so the two never mix and `--clear` only removes its own.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import urllib.request
import uuid
from datetime import date, datetime

import structlog
from sqlalchemy import delete, select

import app.db.base  # noqa: F401 — register models
from app.core.database import session_scope
from app.modules.identity.models import User
from app.modules.research.models import CaseCitation, CourtLevel, Judgment

log = structlog.get_logger("app.ingest_scr")

BUCKET_HOST = "https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com"
METADATA_URL = BUCKET_HOST + "/metadata/parquet/year={year}/metadata.parquet"
PDF_URL = BUCKET_HOST + "/data/pdf/year={year}/english/{path}_EN.pdf"

# Marker used by `seed_sample_corpus.py` on its generated rows. Duplicated here
# rather than imported so this script does not pull in faker.
SAMPLE_HOST = "https://sample.vidhisangh.local"

DEFAULT_YEAR = 2025


def _fetch_year_metadata(year: int) -> list[dict]:
    """Download one year's structured metadata (parquet) over plain HTTPS."""
    import pyarrow.parquet as pq  # imported lazily — only ingestion needs it

    url = METADATA_URL.format(year=year)
    log.info("fetching", url=url)
    with urllib.request.urlopen(url, timeout=120) as resp:
        raw = resp.read()
    return pq.read_table(io.BytesIO(raw)).to_pylist()


def _parse_date(value: str | None) -> date | None:
    """Source dates are DD-MM-YYYY. Note the reporting year can differ from this."""
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _judges(row: dict) -> list[str]:
    """The judge(s) named on the report, comma-separated, without a prefix.

    NOTE this is usually the *authoring* judge alone — 87% of 2025 rows carry a
    single name — not the full bench. So it must not be used to infer bench
    strength; see `_to_judgment`.
    """
    names = [n.strip() for n in (row.get("judge") or "").split(",") if n.strip()]
    author = (row.get("author_judge") or "").strip()
    if author and author not in names:
        names.append(author)
    return [n if n.upper().startswith("JUSTICE") else f"Justice {n.title()}" for n in names]


def _to_judgment(row: dict, year: int, added_by: uuid.UUID) -> dict | None:
    """Map one source record onto a Judgment row, or None if unusable."""
    citation = (row.get("citation") or "").strip()
    title = (row.get("title") or "").strip()
    if not citation or not title:
        return None  # citation is UNIQUE and case_name is NOT NULL

    judges = _judges(row)
    path = (row.get("path") or "").strip()
    return {
        "id": uuid.uuid4(),
        "case_name": title[:500],
        "citation": citation[:200],
        "neutral_citation": ((row.get("case_id") or "").strip() or None),
        "court": (row.get("court") or "Supreme Court of India")[:200],
        "court_level": CourtLevel.SUPREME_COURT.value,
        # Left blank on purpose. `judge` names the authoring judge, not the
        # bench, so counting it would label most Supreme Court cases a "Single
        # Judge" bench — something the Court does not do for reported
        # judgments. Bench strength must come from the judgment text.
        "bench": None,
        "judges": judges,
        "judgment_date": _parse_date(row.get("decision_date")),
        # Not present in the source — see the module docstring.
        "acts": [],
        "sections": [],
        "keywords": [],
        "headnote": None,
        "outcome": ((row.get("disposal_nature") or "").strip() or None),
        "url": PDF_URL.format(year=year, path=path) if path else None,
        "added_by": added_by,
    }


async def _clear(session) -> None:
    like = f"{BUCKET_HOST}%"
    ids = (
        await session.execute(select(Judgment.id).where(Judgment.url.like(like)))
    ).scalars().all()
    if ids:
        await session.execute(
            delete(CaseCitation).where(CaseCitation.from_judgment_id.in_(ids))
        )
    await session.execute(delete(Judgment).where(Judgment.url.like(like)))
    log.info("ingested_cleared", count=len(ids))


async def _purge_sample(session) -> None:
    """Drop the generated corpus from `seed_sample_corpus.py` (judgments only).

    Matched on its marker URL host, so real rows are untouched. Its fake legal
    *news* is left alone — clearing that would empty the Legal News screen with
    nothing to put back; `seed_sample_corpus.py --clear` removes both.
    """
    like = f"{SAMPLE_HOST}%"
    ids = (
        await session.execute(select(Judgment.id).where(Judgment.url.like(like)))
    ).scalars().all()
    if ids:
        await session.execute(
            delete(CaseCitation).where(CaseCitation.from_judgment_id.in_(ids))
        )
        await session.execute(
            delete(CaseCitation).where(CaseCitation.to_judgment_id.in_(ids))
        )
    await session.execute(delete(Judgment).where(Judgment.url.like(like)))
    log.info("sample_judgments_purged", count=len(ids))


async def ingest(
    year_from: int,
    year_to: int,
    count: int,
    clear_only: bool,
    purge_sample: bool,
    dry_run: bool,
) -> None:
    years = list(range(year_from, year_to + 1))

    async with session_scope(bypass_rls=True) as session:
        if clear_only:
            await _clear(session)
            return
        if purge_sample and not dry_run:
            await _purge_sample(session)

        user_id = (await session.execute(select(User.id).limit(1))).scalar_one()

        # Take the SAME leading window every run (parquet row order is stable),
        # then drop what is already stored. Windowing *before* de-duplicating is
        # what makes a re-run a no-op instead of fetching the next N and growing
        # the table on every invocation. `count <= 0` means "the whole year".
        window: list[dict] = []
        skipped_bad = 0
        available = 0
        for year in years:
            rows = _fetch_year_metadata(year)
            available += len(rows)
            taken = 0
            for row in rows:
                if count > 0 and len(window) >= count:
                    break
                mapped = _to_judgment(row, year, user_id)
                if mapped is None:
                    skipped_bad += 1
                    continue
                window.append(mapped)
                taken += 1
            log.info("year_read", year=year, rows=len(rows), taken=taken)
            if count > 0 and len(window) >= count:
                break

        existing = set(
            (await session.execute(select(Judgment.citation))).scalars().all()
        )
        prepared: list[dict] = []
        skipped_dupe = 0
        for mapped in window:
            if mapped["citation"] in existing:
                skipped_dupe += 1
                continue
            existing.add(mapped["citation"])  # guards repeats within the batch too
            prepared.append(mapped)

        log.info(
            "prepared", years=f"{year_from}-{year_to}", ingesting=len(prepared),
            skipped_duplicate=skipped_dupe, skipped_unusable=skipped_bad,
            available=available,
        )
        if dry_run:
            for row in prepared[:10]:
                log.info(
                    "sample", case=row["case_name"][:70], citation=row["citation"],
                    date=str(row["judgment_date"]), outcome=row["outcome"],
                )
            log.info("dry_run_no_writes")
            return

        for start in range(0, len(prepared), 1000):
            await session.execute(
                Judgment.__table__.insert(), prepared[start : start + 1000]
            )
        log.info("judgments_ingested", count=len(prepared))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest real Supreme Court judgments (AWS Open Data, CC-BY-4.0)."
    )
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR, help="Reporting year.")
    parser.add_argument("--year-from", type=int, help="Start of a year range.")
    parser.add_argument("--year-to", type=int, help="End of a year range (inclusive).")
    parser.add_argument(
        "--count", type=int, default=100,
        help="Max rows overall; 0 or less means every judgment in the range.",
    )
    parser.add_argument("--clear", action="store_true", help="Remove ingested rows and exit.")
    parser.add_argument(
        "--purge-sample", action="store_true",
        help="Also delete the generated judgments from seed_sample_corpus.py.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written.")
    args = parser.parse_args()
    year_from = args.year_from if args.year_from is not None else args.year
    year_to = args.year_to if args.year_to is not None else max(year_from, args.year)
    if args.year_from is not None and args.year_to is None:
        year_to = year_from
    asyncio.run(
        ingest(year_from, year_to, args.count, args.clear, args.purge_sample, args.dry_run)
    )


if __name__ == "__main__":  # pragma: no cover
    main()
