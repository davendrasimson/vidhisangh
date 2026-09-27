"""Fill parties, counsel and neutral citations from data already in the table.

    python -m app.scripts.backfill_case_parties            # rows not yet filled
    python -m app.scripts.backfill_case_parties --force    # recompute every row
    python -m app.scripts.backfill_case_parties --court "High Court of Delhi"

Reads each order's cause title and registry description (``headnote``) and
derives, with the same functions the API uses (``app.modules.research.normalise``):

* ``petitioner`` / ``respondent`` — from the cause title ("A Vs B"), all courts.
* ``petitioner_advocates`` / ``respondent_advocates`` / ``advocate_text`` — from
  the order's opening where the registry prints counsel (Delhi "Through:",
  Allahabad "Counsel for … :-", P&H "Present: … for the petitioners").
* ``neutral_citation`` — Allahabad prints it first ("2023:AHC:117096").

Pure read-modify-write in Python, batched; no network. Idempotent: a row is
"done" once ``advocate_text`` or ``petitioner`` is set, unless ``--force``.
Runs in the background on production in well under an hour for 5.6M rows.
"""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid

import structlog
from sqlalchemy import bindparam, select, update
from sqlalchemy.exc import DBAPIError

from app.core.database import session_scope
from app.modules.research.models import Judgment
from app.modules.research.normalise import (
    advocate_text,
    parse_counsel,
    parse_neutral_citation,
    split_parties,
)

log = structlog.get_logger("app.backfill_parties")
_BATCH = 5_000


def derive(cause_title: str | None, case_name: str, headnote: str | None) -> dict:
    petitioner, respondent = split_parties(cause_title or case_name)
    pet_adv, resp_adv = parse_counsel(headnote)
    return {
        "petitioner": petitioner,
        "respondent": respondent,
        "petitioner_advocates": pet_adv,
        "respondent_advocates": resp_adv,
        "advocate_text": advocate_text(pet_adv, resp_adv),
        "neutral_citation": parse_neutral_citation(headnote),
    }


async def backfill(force: bool, court: str | None, refresh_where: str | None = None) -> None:
    started = time.monotonic()
    done = with_counsel = 0
    last_id: uuid.UUID | None = None

    async with session_scope(bypass_rls=True) as session:
        while True:
            q = (
                select(
                    Judgment.id, Judgment.cause_title, Judgment.case_name,
                    Judgment.headnote, Judgment.neutral_citation,
                )
                .where(Judgment.deleted_at.is_(None))
                .order_by(Judgment.id)
                .limit(_BATCH)
            )
            if last_id is not None:
                q = q.where(Judgment.id > last_id)
            if court:
                q = q.where(Judgment.court == court)
            if refresh_where:
                # Re-derive only rows whose current counsel matches a pattern —
                # e.g. '\(' after a parser fix for parentheticals — instead of
                # a full --force pass over the corpus.
                q = q.where(Judgment.advocate_text.op("~")(refresh_where))
            elif not force:
                q = q.where(Judgment.advocate_text.is_(None), Judgment.petitioner.is_(None))
            rows = (await session.execute(q)).all()
            if not rows:
                break

            params = []
            for jid, cause_title, case_name, headnote, neutral in rows:
                d = derive(cause_title, case_name, headnote)
                # Never overwrite a neutral citation the SC loader set.
                d["neutral_citation"] = neutral or d["neutral_citation"]
                d["_id"] = jid
                params.append(d)
                with_counsel += bool(d["advocate_text"])
            # Core table, not the ORM entity: an ORM `update()` run with a list
            # of parameter dicts switches into "bulk update by primary key"
            # mode and wants `id` keys, and otherwise insists on synchronising
            # an identity map we never populated. Core executemany just runs.
            t = Judgment.__table__
            stmt = (
                update(t)
                .where(t.c.id == bindparam("_id"))
                .values(
                    petitioner=bindparam("petitioner"),
                    respondent=bindparam("respondent"),
                    petitioner_advocates=bindparam("petitioner_advocates"),
                    respondent_advocates=bindparam("respondent_advocates"),
                    advocate_text=bindparam("advocate_text"),
                    neutral_citation=bindparam("neutral_citation"),
                )
            )
            # Another bulk job (e.g. the filing-date backfill) may lock the same
            # rows in a different order; Postgres aborts one side (40P01).
            # Retrying the batch is always safe — each batch is one transaction.
            for attempt in range(5):
                try:
                    await session.execute(stmt, params)
                    await session.commit()
                    break
                except DBAPIError as exc:
                    await session.rollback()
                    if getattr(getattr(exc, "orig", None), "sqlstate", None) != "40P01" or attempt == 4:
                        raise
                    log.warning("deadlock_retry", attempt=attempt + 1, rows=len(params))
                    await asyncio.sleep(2 * (attempt + 1))

            last_id = rows[-1][0]
            done += len(rows)
            if done % 100_000 == 0:
                log.info("progress", rows=done, with_counsel=with_counsel,
                         minutes=round((time.monotonic() - started) / 60, 1))

    log.info("finished", rows=done, with_counsel=with_counsel,
             minutes=round((time.monotonic() - started) / 60, 1))


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill case parties, counsel, neutral citations.")
    parser.add_argument("--force", action="store_true", help="Recompute rows already filled.")
    parser.add_argument("--court", help="Only this court (exact `court` value).")
    parser.add_argument(
        "--refresh-where",
        help="Re-derive only rows whose advocate_text matches this Postgres regex.",
    )
    args = parser.parse_args()
    asyncio.run(backfill(args.force, args.court, args.refresh_where))


if __name__ == "__main__":
    main()
