"""Create or clear the guided sample workspace for one tenant."""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

import app.db.base  # noqa: F401
from app.core.database import session_scope
from app.core.storage import get_storage
from app.modules.identity.models import User
from app.modules.sampledata.service import SampleDataService


async def run(email: str, clear: bool) -> None:
    async with session_scope(bypass_rls=True) as session:
        user = (
            await session.execute(select(User).where(User.email == email.lower()))
        ).scalar_one()
        service = SampleDataService(session, user.tenant_id, user.id, get_storage())
        result = await (service.clear() if clear else service.create())
        print(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage a tenant's guided sample workspace.")
    parser.add_argument("--email", required=True, help="Tenant owner email address")
    parser.add_argument("--clear", action="store_true", help="Remove registered sample rows")
    args = parser.parse_args()
    asyncio.run(run(args.email, args.clear))


if __name__ == "__main__":
    main()
