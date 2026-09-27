"""Retention purge — delete data past its retention period.

Run with:  ``python -m app.scripts.retention_purge [--dry-run]``

Each purge is a coroutine ``(session) -> int`` (rows removed) appended to
:data:`PURGES`; add new ones here as retention rules are defined (DPDP s.8(7),
audit P-1 / P-12 / P-14). Every purge runs in its own bypass-RLS transaction so
one failure never rolls back the others. Schedule nightly (cron / systemd timer).
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.base  # noqa: F401 — register all models
from app.core.database import session_scope
from app.modules.notifications.service import DELIVERY_RETENTION_DAYS, purge_old_deliveries
from app.modules.privacy.retention import PRIVACY_PURGES

log = structlog.get_logger("app.retention_purge")

Purge = Callable[[AsyncSession], Awaitable[int]]


async def purge_notification_deliveries(session: AsyncSession) -> int:
    """Notification delivery log: keep 90 days (audit P-12)."""
    return await purge_old_deliveries(session, days=DELIVERY_RETENTION_DAYS)


# Registry — other modules append their purges here (privacy work, P-1/P-14).
PURGES: list[Purge] = [
    purge_notification_deliveries,
    # Privacy agent (P-1/P-14): oauth states, passkey challenges, revoked/expired
    # sessions, used backup codes, soft-deleted documents (+ object-store bytes)
    # and drafts, old notifications, cancelled tenants past `erase_after`.
    *PRIVACY_PURGES,
]


async def run_all(*, dry_run: bool = False) -> dict[str, int]:
    """Run every registered purge; returns ``{purge_name: rows_removed}``."""
    results: dict[str, int] = {}
    for purge in PURGES:
        name = purge.__name__
        try:
            async with session_scope(bypass_rls=True) as session:
                removed = await purge(session)
                if dry_run:
                    await session.rollback()
                results[name] = removed
                log.info("purge_done", purge=name, removed=removed, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001 - keep going; report at the end
            log.error("purge_failed", purge=name, error=type(exc).__name__)
            results[name] = -1
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="count but roll back")
    args = parser.parse_args()
    results = asyncio.run(run_all(dry_run=args.dry_run))
    for name, removed in results.items():
        print(f"{name}: {'FAILED' if removed < 0 else removed}")


if __name__ == "__main__":
    main()
