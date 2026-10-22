"""Raise due retainer periods and dated milestones (systemd timer vidhisangh-fee-sweep).

    python -m app.scripts.fee_sweep            # raise them
    python -m app.scripts.fee_sweep --dry-run  # counts only, rolled back

Prints counts only: no client names, matters or amounts.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.database import session_scope
from app.modules.matters.fee_sweep import sweep


async def run(dry_run: bool) -> dict:
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    async with session_scope(bypass_rls=True) as session:
        result = await sweep(session, today)
        if dry_run:
            await session.rollback()
    return {"day": today.isoformat(), "dry_run": dry_run, **result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    print(asyncio.run(run(parser.parse_args().dry_run)))
