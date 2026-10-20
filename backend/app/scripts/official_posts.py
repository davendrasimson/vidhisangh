"""Post today's official VidhiSangh feed items (systemd timer vidhisangh-official-posts).

    python -m app.scripts.official_posts            # post (each item once, each kind once a day)
    python -m app.scripts.official_posts --dry-run  # what would go out, nothing written
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import session_scope
from app.modules.network import official


async def run(dry_run: bool) -> dict:
    async with session_scope(bypass_rls=True) as session:
        report = await official.post_daily(session)
        if dry_run:
            await session.rollback()
            return {"dry_run": True, **report}
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    print(asyncio.run(run(parser.parse_args().dry_run)))
