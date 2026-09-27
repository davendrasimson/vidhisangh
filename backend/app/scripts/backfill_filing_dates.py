"""Fill ``filed_on`` (the registry's date of registration) for High Court orders.

    python -m app.scripts.backfill_filing_dates --courts phhc,delhi,allahabad
    python -m app.scripts.backfill_filing_dates --courts delhi --year-from 2020

The first ingest dropped ``date_of_registration``; it is in every metadata
parquet file (100% of rows), so this re-streams the metadata — never the PDFs —
and matches rows by ``source_ref`` (``<court code>:<cnr>:<decision date>``),
the same key the ingest de-duplicates on.

Per file: rows are loaded into an UNLOGGED staging table and applied with one
``UPDATE … FROM``, which is far faster than per-row updates at this scale.
Idempotent: only rows whose ``filed_on`` is NULL are touched.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime

import structlog
from sqlalchemy import text

from app.core.database import session_scope
from app.scripts.ingest_hc_judgments import (
    BUCKET,
    COURTS,
    _list_keys,
    _parse_date,
    _parse_registration,
)

log = structlog.get_logger("app.backfill_filing")

_STAGING = """
CREATE UNLOGGED TABLE IF NOT EXISTS _filing_dates (
    source_ref varchar(120) PRIMARY KEY,
    filed_on   date NOT NULL
)
"""
_APPLY = """
UPDATE judgments j SET filed_on = s.filed_on
FROM _filing_dates s
WHERE j.source_ref = s.source_ref AND j.filed_on IS NULL
"""


async def backfill(courts: list[str], year_from: int, year_to: int) -> None:
    import pyarrow.parquet as pq  # lazy — only ingestion needs it

    wanted = {COURTS[c][0] for c in courts}
    selected = []
    for key in _list_keys():
        cm = re.search(r"court=([^/]+)/", key)
        ym = re.search(r"year=(\d{4})", key)
        if cm and ym and cm.group(1) in wanted and year_from <= int(ym.group(1)) <= year_to:
            selected.append((int(ym.group(1)), cm.group(1), key))
    selected.sort(reverse=True)
    log.info("files_selected", files=len(selected))

    started = time.monotonic()
    applied = 0
    async with session_scope(bypass_rls=True) as session:
        await session.execute(text(_STAGING))
        await session.commit()
        for year, code, key in selected:
            raw = urllib.request.urlopen(f"{BUCKET}/{urllib.parse.quote(key)}", timeout=900).read()
            table = pq.read_table(io.BytesIO(raw), columns=["cnr", "decision_date", "date_of_registration"])
            rows: dict[str, date] = {}
            for rec in table.to_pylist():
                cnr = (rec.get("cnr") or "").strip()
                filed = _parse_registration(rec.get("date_of_registration"))
                if not cnr or filed is None:
                    continue
                decided = _parse_date(rec.get("decision_date"))
                rows[f"{code}:{cnr}:{decided or 'na'}"[:120]] = filed
            if not rows:
                continue
            await session.execute(text("TRUNCATE _filing_dates"))
            params = [{"r": r, "f": f} for r, f in rows.items()]
            for i in range(0, len(params), 20_000):
                await session.execute(
                    text("INSERT INTO _filing_dates (source_ref, filed_on) VALUES (:r, :f) "
                         "ON CONFLICT DO NOTHING"),
                    params[i : i + 20_000],
                )
            res = await session.execute(text(_APPLY))
            await session.commit()
            applied += res.rowcount or 0
            log.info("file_applied", year=year, court=code, staged=len(rows),
                     updated=res.rowcount, total=applied,
                     minutes=round((time.monotonic() - started) / 60, 1))
        await session.execute(text("DROP TABLE IF EXISTS _filing_dates"))
        await session.commit()
    log.info("finished", updated=applied, minutes=round((time.monotonic() - started) / 60, 1))


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill High Court filing dates from metadata.")
    parser.add_argument("--courts", default="phhc,delhi,allahabad")
    parser.add_argument("--year-from", type=int, default=1950)
    parser.add_argument("--year-to", type=int, default=date.today().year)
    args = parser.parse_args()
    asyncio.run(backfill([c.strip() for c in args.courts.split(",") if c.strip()], args.year_from, args.year_to))


if __name__ == "__main__":
    main()
