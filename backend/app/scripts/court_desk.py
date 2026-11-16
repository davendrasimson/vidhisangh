"""Court desk (systemd timer vidhisangh-court-desk, 06:45 and 18:00 IST Mon-Sat).

    python -m app.scripts.court_desk            # read each court's cause-list index, record the lists
                                                # for today and later days, post new days to the court's group
    python -m app.scripts.court_desk --dry-run  # show what each court's index says; nothing written

Only public index pages are read; no list is opened and no search is submitted
(see app/modules/courts/fetch.py).
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import session_scope
from app.modules.courts import fetch as fetching
from app.modules.courts import service
from app.modules.courts.registry import COURTS


async def run(dry_run: bool) -> dict:
    today = service.today_ist()
    async with fetching.client() as http:
        if dry_run:
            out: dict = {"today": today.isoformat()}
            for court in COURTS:
                if not court.fetcher:
                    continue
                try:
                    found = await fetching.fetch(http, court)
                except Exception as exc:  # noqa: BLE001
                    out[court.slug] = f"failed: {type(exc).__name__}: {exc}"[:200]
                    continue
                out[court.slug] = {d.isoformat(): [l["label"] for l in lists] for d, lists in sorted(found.items())}
            return out
        async with session_scope(bypass_rls=True) as session:
            fetched = await service.refresh(session, http, today)
            posted = await service.post_new(session)
    return {"today": today.isoformat(), "fetched": fetched, "posted": posted}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    print(asyncio.run(run(parser.parse_args().dry_run)))
