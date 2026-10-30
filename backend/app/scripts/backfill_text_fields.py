"""Fill acts / sections and counsel for rows that already have their order text.

The High Court registries never carry the statutes cited; `extract_order_text`
parses them from the PDF text as it extracts, but the rows extracted before
that step existed (Delhi 2024–25, ~128k) and Uttarakhand's text rows still have
``acts = []``, and many have no counsel either. This re-runs
``parse_acts_sections`` and ``parse_counsel`` over the stored ``full_text`` —
no PDFs, no network — in id order, committing a batch at a time, so it can be
stopped and resumed.

  python -m app.scripts.backfill_text_fields --limit 500 --dry-run
  python -m app.scripts.backfill_text_fields --court "High Court of Delhi"
  python -m app.scripts.backfill_text_fields                 # every court, everything left
"""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid

from sqlalchemy import String, cast, or_, select

import app.db.base  # noqa: F401 — register models
from app.core.database import session_scope
from app.modules.research.models import CourtLevel, Judgment
from app.modules.research.normalise import advocate_text, parse_acts_sections, parse_counsel


def enrich_row(j: Judgment) -> tuple[bool, bool]:
    """Fill the empty fields from the text in place. Returns (acts_filled, counsel_filled)."""
    text = j.full_text or ""
    acts_filled = counsel_filled = False
    if not j.acts:
        acts, sections = parse_acts_sections(text)
        if acts:
            j.acts, j.sections = acts, sections
            acts_filled = True
    if not j.advocate_text:
        pet, resp = parse_counsel(text[:1500])
        if pet or resp:
            j.petitioner_advocates, j.respondent_advocates = pet, resp
            j.advocate_text = advocate_text(pet, resp)
            counsel_filled = True
    return acts_filled, counsel_filled


async def backfill(*, court: str | None, limit: int, batch: int, dry_run: bool, log=print) -> dict[str, int]:  # noqa: ANN001
    stats = {"seen": 0, "acts": 0, "counsel": 0}
    last: uuid.UUID | None = None
    started = time.monotonic()
    while True:
        async with session_scope(bypass_rls=True) as session:
            stmt = (
                select(Judgment)
                .where(
                    Judgment.deleted_at.is_(None),
                    Judgment.court_level == CourtLevel.HIGH_COURT,
                    Judgment.full_text.is_not(None),
                    or_(cast(Judgment.acts, String) == "[]", Judgment.advocate_text.is_(None)),
                )
                .order_by(Judgment.id)
                .limit(batch)
            )
            if court:
                stmt = stmt.where(Judgment.court == court)
            if last is not None:
                stmt = stmt.where(Judgment.id > last)
            rows = list((await session.execute(stmt)).scalars().all())
            if not rows:
                break
            for j in rows:
                a, c = enrich_row(j)
                stats["seen"] += 1
                stats["acts"] += a
                stats["counsel"] += c
            last = rows[-1].id
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
        log(f"{stats['seen']} rows: acts filled {stats['acts']}, counsel filled {stats['counsel']} "
            f"({round(time.monotonic() - started)} s)")
        if limit and stats["seen"] >= limit:
            break
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--court", help="Only this court (the judgments.court value).")
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many rows (0 = all).")
    parser.add_argument("--batch", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true", help="Parse and count, write nothing.")
    args = parser.parse_args()
    print(asyncio.run(backfill(court=args.court, limit=args.limit, batch=args.batch, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
