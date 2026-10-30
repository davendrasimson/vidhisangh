"""Mine parallel citations (SCC, AIR, …) for library judgments from judgment texts.

  python -m app.scripts.parallel_citations mine [--limit N] [--min-support 1] [--dry-run]
  python -m app.scripts.parallel_citations status

See app.modules.research.parallel_citations. Idempotent: an alias is created
once per citation and its support updated on re-runs; curated rows are left alone.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from sqlalchemy import func, select

import app.db.base  # noqa: F401 — register models
from app.core.database import session_scope
from app.modules.research.models import JudgmentAlias
from app.modules.research.parallel_citations import mine


async def _status() -> None:
    async with session_scope(bypass_rls=True) as session:
        rows = (await session.execute(
            select(JudgmentAlias.reporter, func.count(), func.sum(JudgmentAlias.support))
            .where(JudgmentAlias.deleted_at.is_(None)).group_by(JudgmentAlias.reporter).order_by(func.count().desc())
        )).all()
        total = sum(n for _, n, _ in rows)
        print(f"{total} aliases")
        for reporter, n, support in rows:
            print(f"  {reporter:<10} {n:>7} aliases, {int(support or 0):>8} citing judgments")


async def _mine(limit: int | None, min_support: int, dry_run: bool) -> None:
    t = time.time()
    async with session_scope(bypass_rls=True) as session:
        stats = await mine(session, limit=limit, min_support=min_support)
        if dry_run:
            await session.rollback()
            print("dry run: nothing written")
        print({**stats, "seconds": round(time.time() - t)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    m = sub.add_parser("mine")
    m.add_argument("--limit", type=int, help="only the N newest judgments with text")
    m.add_argument("--min-support", type=int, default=1, help="citing judgments needed before an alias is written")
    m.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.cmd == "status":
        asyncio.run(_status())
    else:
        asyncio.run(_mine(args.limit, args.min_support, args.dry_run))


if __name__ == "__main__":
    main()
