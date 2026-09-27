"""Fill the structured research fields added in migration 0036.

Run:  python -m app.scripts.backfill_case_fields            # everything unfilled
      python -m app.scripts.backfill_case_fields --force    # recompute all rows

Derives, per judgment:

* ``case_type`` / ``case_number`` / ``case_year`` / ``cause_title`` from the
  registry title. High Court titles read ``CRM-M/33310/2019 of RUSTAM Vs STATE``;
  Supreme Court titles have no number prefix, so their cause title is the
  title itself and ``case_year`` falls back to the decision year.
* ``judge_text`` from ``judges``: honorifics stripped, title-cased, " | "-joined.

Pure SQL, batched per court so no single transaction holds 5.6M row locks,
and idempotent — rows already filled are skipped unless ``--force``. Because
``search_vector`` is a generated column, Postgres refreshes it as each row is
updated; nothing here touches it directly.
"""

from __future__ import annotations

import argparse
import asyncio

import structlog
from sqlalchemy import text

import app.db.base  # noqa: F401 — register models
from app.core.database import session_scope

log = structlog.get_logger("app.backfill_case_fields")

_TITLE_RE = r"^([^/]+)/(\d+)/(\d{4})\s+of\s+"

# Honorifics as the registries print them; what remains is the bare name.
# "HON'BLE THE CHIEF JUSTICE", "MR. JUSTICE", "SMT. JUSTICE", "ACTING CHIEF JUSTICE"…
# Trailing whitespace optional (\y = word boundary in Postgres ARE) so a bare
# "HON'BLE THE ACTING CHIEF JUSTICE" strips to '' and is dropped, not kept as a name.
_JUDGE_STRIP_RE = (
    r"^(HON'?BLE\s+)?(THE\s+)?((MR|MRS|MS|DR|SHRI|SMT)\.?\s+)?"
    r"((ACTING\s+)?(CHIEF\s+)?JUSTICE\y\s*)?"
)
# One registry element may name several judges: "A, HON'BLE MR. JUSTICE B".
_JUDGE_SPLIT_RE = r"\s*,\s*|\s+and\s+|\s*&\s*"

_UPDATE = f"""
UPDATE judgments SET
    case_type   = COALESCE(NULLIF(left((regexp_match(case_name, :title_re))[1], 40), ''), case_type),
    case_number = COALESCE(left((regexp_match(case_name, :title_re))[2], 40), case_number),
    case_year   = COALESCE(
                    (regexp_match(case_name, :title_re))[3]::int,
                    case_year,
                    EXTRACT(YEAR FROM judgment_date)::int),
    cause_title = left(regexp_replace(case_name, :title_re, ''), 500),
    judge_text  = NULLIF((
        SELECT string_agg(name, ' | ' ORDER BY name)
        FROM (
            SELECT DISTINCT initcap(regexp_replace(trim(piece), :judge_re, '', 'i')) AS name
            FROM json_array_elements_text(judges) AS j,
                 regexp_split_to_table(j, :split_re, 'i') AS piece
            WHERE trim(piece) <> ''
        ) names
        WHERE name <> ''
    ), '')
WHERE court = :court
  {{extra}}
"""


async def backfill(force: bool) -> None:
    async with session_scope(bypass_rls=True) as session:
        courts = (
            await session.execute(
                text("SELECT court, count(*) FROM judgments GROUP BY court ORDER BY 2")
            )
        ).all()
        extra = "" if force else "AND cause_title IS NULL"
        stmt = text(_UPDATE.format(extra=extra))

        total = 0
        for court, count in courts:
            result = await session.execute(
                stmt,
                {"court": court, "title_re": _TITLE_RE,
                 "judge_re": _JUDGE_STRIP_RE, "split_re": _JUDGE_SPLIT_RE},
            )
            await session.commit()
            total += result.rowcount
            log.info("court_done", court=court, rows=result.rowcount, of=count)

        log.info("backfill_complete", updated=total)

        sample = (
            await session.execute(
                text(
                    "SELECT case_type, case_number, case_year, left(cause_title, 50), judge_text "
                    "FROM judgments WHERE case_type IS NOT NULL ORDER BY random() LIMIT 3"
                )
            )
        ).all()
        for row in sample:
            log.info("sample", **dict(zip(("type", "num", "year", "title", "judges"), row)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill structured research fields.")
    parser.add_argument("--force", action="store_true", help="Recompute rows already filled.")
    args = parser.parse_args()
    asyncio.run(backfill(args.force))


if __name__ == "__main__":  # pragma: no cover
    main()
