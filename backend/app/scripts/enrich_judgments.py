"""Fill in acts / sections / keywords / bench / headnote for ingested judgments.

Downloads each judgment's PDF from the open bucket it was ingested from and
runs `app.core.judgment_enrichment` over the text. Only rows ingested by
`ingest_scr_judgments.py` are touched — generated sample rows are skipped.

Run:  python -m app.scripts.enrich_judgments --limit 200
      python -m app.scripts.enrich_judgments --limit 0            # everything left
      python -m app.scripts.enrich_judgments --limit 20 --dry-run
      python -m app.scripts.enrich_judgments --limit 50 --force   # redo enriched rows

By default only rows with no headnote are processed, so the job is resumable:
stop it and re-run, and it picks up where it left off. ~13k judgments is a few
GB of PDFs, so start small.
"""

from __future__ import annotations

import argparse
import asyncio

import httpx
import structlog
from sqlalchemy import select, update

import app.db.base  # noqa: F401 — register models
from app.core.database import session_scope
from app.core.judgment_enrichment import extract_text, get_judgment_enricher
from app.modules.research.models import Judgment

log = structlog.get_logger("app.enrich_judgments")

BUCKET_HOST = "https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com"
_TIMEOUT = 60.0
_BATCH = 200  # rows per commit — small enough that an interruption loses little


async def _fetch(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        log.warning("pdf_fetch_failed", url=url, error=str(exc))
        return None


async def _process(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, row: tuple
) -> dict | None:
    judgment_id, url = row
    async with sem:
        pdf = await _fetch(client, url)
    if not pdf:
        return None
    # PDF parsing is CPU-bound; keep it off the event loop.
    text = await asyncio.to_thread(extract_text, pdf)
    if not text.strip():
        return None
    found = get_judgment_enricher().enrich(text)
    if found.is_empty():
        return None

    values: dict = {"id": judgment_id}
    if found.acts:
        values["acts"] = found.acts
    if found.sections:
        values["sections"] = found.sections
    if found.keywords:
        values["keywords"] = found.keywords
    if found.bench:
        values["bench"] = found.bench
    # The coram is the real bench; the ingested `judges` held only the author.
    if found.judges:
        values["judges"] = found.judges
    if found.headnote:
        values["headnote"] = found.headnote
    return values if len(values) > 1 else None


async def enrich(limit: int, concurrency: int, force: bool, dry_run: bool) -> None:
    async with session_scope(bypass_rls=True) as session:
        stmt = select(Judgment.id, Judgment.url).where(
            Judgment.url.like(f"{BUCKET_HOST}%"), Judgment.deleted_at.is_(None)
        )
        if not force:
            stmt = stmt.where(Judgment.headnote.is_(None))
        stmt = stmt.order_by(Judgment.judgment_date.desc())
        if limit > 0:
            stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).all()

        log.info("to_enrich", count=len(rows), concurrency=concurrency, force=force)
        if not rows:
            return

        # Work in batches and commit each one. A full pass is thousands of PDF
        # downloads; buffering it all and writing once at the end would mean an
        # interruption threw away every result and made "resumable" a lie.
        sem = asyncio.Semaphore(concurrency)
        done = written = 0
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            for start in range(0, len(rows), _BATCH):
                batch = rows[start : start + _BATCH]
                results = await asyncio.gather(
                    *(_process(client, sem, row) for row in batch)
                )
                updates = [r for r in results if r]
                done += len(batch)

                if dry_run:
                    for row in updates[:5]:
                        log.info(
                            "sample", bench=row.get("bench"),
                            acts=row.get("acts", [])[:3],
                            sections=row.get("sections", [])[:4],
                            keywords=row.get("keywords", [])[:4],
                            headnote=(row.get("headnote") or "")[:160],
                        )
                    log.info("dry_run_no_writes", would_update=len(updates))
                    return

                if updates:
                    await session.execute(update(Judgment), updates)
                    await session.commit()
                    written += len(updates)
                log.info(
                    "progress", processed=done, of=len(rows), written=written,
                    skipped=done - written,
                )

        log.info("judgments_updated", count=written, processed=done)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich ingested judgments from their source PDFs."
    )
    parser.add_argument(
        "--limit", type=int, default=200,
        help="Max judgments this run; 0 or less means all remaining.",
    )
    parser.add_argument(
        "--concurrency", type=int, default=8, help="Parallel PDF downloads."
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-enrich rows that already have a headnote."
    )
    parser.add_argument("--dry-run", action="store_true", help="Show results, write nothing.")
    args = parser.parse_args()
    asyncio.run(enrich(args.limit, args.concurrency, args.force, args.dry_run))


if __name__ == "__main__":  # pragma: no cover
    main()
