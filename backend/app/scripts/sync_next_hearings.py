"""One-off: set each matter's "Next hearing" from its recorded hearings.

Before 14 Oct 2026, adding a hearing did not update the matter, so matters with
hearings could still show "Next hearing: Not scheduled". New and changed
hearings now keep it in step (MatterService._sync_next_hearing); this applies
the same rule once to every matter that has hearings.

  python -m app.scripts.sync_next_hearings            # dry run: report only
  python -m app.scripts.sync_next_hearings --apply
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import select

import app.db.base  # noqa: F401 — register models
from app.core.database import session_scope
from app.modules.matters.models import Hearing, Matter
from app.modules.matters.service import MatterService


async def main(apply: bool) -> None:
    async with session_scope(bypass_rls=True) as session:
        rows = (await session.execute(
            select(Matter.id, Matter.tenant_id, Matter.next_hearing_date)
            .where(Matter.deleted_at.is_(None), Matter.id.in_(select(Hearing.matter_id).where(Hearing.deleted_at.is_(None))))
        )).all()
        changed = 0
        for matter_id, tenant_id, before in rows:
            service = MatterService(session, uuid.UUID(int=0), tenant_id)
            await service._sync_next_hearing(matter_id)
            after = (await service._require_matter(matter_id)).next_hearing_date
            if after != before:
                changed += 1
                print(f"{matter_id}: {before} -> {after}")
        print(f"{len(rows)} matters with hearings, {changed} changed ({'applied' if apply else 'dry run, nothing saved'})")
        if not apply:
            await session.rollback()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="save the changes (default: report only)")
    asyncio.run(main(parser.parse_args().apply))
