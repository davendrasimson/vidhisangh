"""Extract Supreme Court judgment text into ``judgments.full_text``.

    python -m app.scripts.extract_sc_text            # every SC row not yet done
    python -m app.scripts.extract_sc_text --limit 50 # pilot

The SC rows link to SCR (Supreme Court Reports) volume PDFs, fetched one by
one over HTTPS (200 KB–1 MB each; ~19 GB for all 38k, streamed, never kept).

**Copyright:** an SCR PDF opens with the reporter's headnote, index and
keywords — the publisher's work (EBC v. D.B. Modak). Only the judgment is
stored (``sc_judgment_body`` cuts at the jurisdiction/"Case Arising From"
line); where that boundary cannot be found the row is marked extracted with
no text rather than risk copying the headnote. Counsel comes from the
appearance block that precedes the judgment; acts/sections only fill rows
that have none (the curated SC values are better than a regex pass).
"""

from __future__ import annotations

import argparse
import asyncio
import re
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime

import structlog
from sqlalchemy import Text, bindparam, cast, select, update

from app.core.database import session_scope
from app.modules.research.models import CourtLevel, Judgment
from app.modules.research.normalise import (
    advocate_text,
    parse_acts_sections,
    parse_sc_counsel,
    sc_judgment_body,
)
from app.scripts.extract_order_text import pdf_text

log = structlog.get_logger("app.extract_sc")
_BATCH = 50


def fetch_and_extract(url: str) -> str:
    """Download one SCR PDF and return the judgment body text ('' if none)."""
    try:
        data = urllib.request.urlopen(url, timeout=300).read()
    except Exception:  # noqa: BLE001 — a missing file must not stop the run
        return ""
    return sc_judgment_body(pdf_text(data)) or ""


async def _flush(session, rows: list[dict]) -> None:  # noqa: ANN001
    t = Judgment.__table__
    now = datetime.now(UTC)
    await session.execute(
        update(t).where(t.c.id == bindparam("_id")).values(full_text=bindparam("text"), text_extracted_at=now),
        [{"_id": r["id"], "text": r["text"]} for r in rows],
    )
    counsel = [r for r in rows if r.get("adv")]
    if counsel:
        await session.execute(
            update(t).where(t.c.id == bindparam("_id"), t.c.advocate_text.is_(None)).values(
                petitioner_advocates=bindparam("pet"), respondent_advocates=bindparam("resp"),
                advocate_text=bindparam("adv"),
            ),
            [{"_id": r["id"], "pet": r["pet"], "resp": r["resp"], "adv": r["adv"]} for r in counsel],
        )
    cited = [r for r in rows if r.get("acts")]
    if cited:
        await session.execute(
            update(t).where(t.c.id == bindparam("_id"), cast(t.c.acts, Text) == "[]").values(
                acts=bindparam("acts"), sections=bindparam("sections")
            ),
            [{"_id": r["id"], "acts": r["acts"], "sections": r["sections"]} for r in cited],
        )
    await session.commit()


async def extract(force: bool, limit: int, workers: int) -> None:
    started = time.monotonic()
    done = empty = with_counsel = 0
    pool = ProcessPoolExecutor(max_workers=workers)
    async with session_scope(bypass_rls=True) as session:
        q = (
            select(Judgment.id, Judgment.url)
            .where(Judgment.deleted_at.is_(None), Judgment.court_level == CourtLevel.SUPREME_COURT,
                   Judgment.url.isnot(None))
            .order_by(Judgment.judgment_date.desc().nulls_last())
        )
        if not force:
            q = q.where(Judgment.text_extracted_at.is_(None))
        if limit:
            q = q.limit(limit)
        todo = (await session.execute(q)).all()
        log.info("rows_selected", rows=len(todo))

        for i in range(0, len(todo), _BATCH):
            chunk = todo[i : i + _BATCH]
            texts = list(pool.map(fetch_and_extract, [url for _, url in chunk]))
            rows = []
            for (jid, _), text in zip(chunk, texts):
                row: dict = {"id": jid, "text": text}
                if text:
                    pet, resp = parse_sc_counsel(text[:6000])
                    if pet or resp:
                        row.update(pet=pet, resp=resp, adv=advocate_text(pet, resp))
                    # Older SCR volumes interleave A–H margin letters with the
                    # text ("Indian F Penal Code"); drop them for parsing only.
                    acts, sections = parse_acts_sections(
                        re.sub(r"(?<![A-Za-z.])[A-H](?![A-Za-z.])", " ", text)
                    )
                    if acts:
                        row.update(acts=acts, sections=sections)
                else:
                    empty += 1
                rows.append(row)
            await _flush(session, rows)
            done += len(rows)
            with_counsel += sum(1 for r in rows if r.get("adv"))
            if done % 500 < _BATCH:
                log.info("progress", extracted=done, empty=empty, with_counsel=with_counsel,
                         minutes=round((time.monotonic() - started) / 60, 1))
    pool.shutdown()
    log.info("finished", extracted=done, empty=empty, with_counsel=with_counsel,
             minutes=round((time.monotonic() - started) / 60, 1))


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Supreme Court judgment text (SCR volumes).")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(extract(args.force, args.limit, args.workers))


if __name__ == "__main__":
    main()
