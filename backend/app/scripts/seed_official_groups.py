"""Create the official community groups (idempotent; rerun after adding to GROUPS).

    python -m app.scripts.seed_official_groups
"""

from __future__ import annotations

import asyncio

from app.core.database import session_scope
from app.modules.groups import official


async def run() -> dict:
    async with session_scope(bypass_rls=True) as session:
        return await official.seed(session)


if __name__ == "__main__":
    print(asyncio.run(run()))
