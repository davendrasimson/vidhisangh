"""Retrieve official orders, export for offline headnote writing, email subscribers.

Default is a read-only discovery preview. --execute performs intake/extraction;
--send additionally sends email. Both require VS_SC_DAILY_ENABLED=true.
--send-only delivers headnotes imported through the established offline flow.
Delivery is the email digest, then the WhatsApp digest (template sc_daily_orders)
to members who said yes to WhatsApp updates, once per member per IST day.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import text

import app.db.base  # noqa: F401
from app.core.channels import EmailSmtpProvider
from app.core.config import settings
from app.core.database import get_engine, session_scope
from app.core.whatsapp import get_whatsapp_sender
from app.modules.research.daily_orders import (
    IST,
    export_pending,
    prepare_headnotes,
    register_entries,
    send_digests,
)
from app.modules.research.daily_source import SupremeCourtSource
from app.modules.research.daily_whatsapp import send_whatsapp_digests


async def run(
    *,
    execute: bool = False,
    send: bool = False,
    send_only: bool = False,
    export_dir: Path | None = None,
) -> dict:
    if (send or send_only or export_dir is not None) and not execute:
        raise ValueError("Sending/exporting requires --execute")
    if execute and not settings.SC_DAILY_ENABLED:
        raise ValueError("Enable VS_SC_DAILY_ENABLED before executing the job")
    now = datetime.now(UTC)
    # A dedicated connection retains this session-level lock across the job's
    # short DB commits. Competing cron/manual runs exit before any model/SMTP I/O.
    async with get_engine().connect() as lock:
        postgres = lock.dialect.name == "postgresql"
        if postgres:
            acquired = await lock.scalar(text("SELECT pg_try_advisory_lock(73663001)"))
            await lock.commit()
            if not acquired:
                return {"skipped": "daily order job already running"}
        try:
            async with httpx.AsyncClient(
                timeout=45,
                follow_redirects=False,
                headers={"User-Agent": "VidhiSangh official-order reader/1.0"},
            ) as client:
                source = SupremeCourtSource(client)
                entries = [] if send_only else await source.discover()
                report = {"day": now.astimezone(IST).date().isoformat(), "discovered": len(entries)}
                if not execute:
                    return {**report, "preview": True, "database_writes": 0, "emails_sent": 0}
                async with session_scope(bypass_rls=True) as session:
                    if not send_only:
                        report["added"] = await register_entries(session, entries, now)
                        report.update(await prepare_headnotes(session, source))
                    if export_dir is not None:
                        report["exported_for_writing"] = await export_pending(session, export_dir)
                    if send or send_only:
                        day = now.astimezone(IST).date()
                        sender = EmailSmtpProvider()
                        if not sender.configured:
                            report["email_skipped"] = "SMTP is not configured"
                        else:
                            report["email"] = await send_digests(session, sender, day)
                        # WhatsApp follows the email: the same orders, to members who said yes to
                        # WhatsApp updates (needs the number's token in the unit's environment).
                        whatsapp = get_whatsapp_sender()
                        if whatsapp is None:
                            report["whatsapp_skipped"] = "WhatsApp is not configured"
                        else:
                            report["whatsapp"] = await send_whatsapp_digests(session, whatsapp, day)
                    return report
        finally:
            if postgres:
                await lock.execute(text("SELECT pg_advisory_unlock(73663001)"))
                await lock.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--send-only", action="store_true")
    parser.add_argument("--export-pending", type=Path)
    args = parser.parse_args()
    result = asyncio.run(
        run(
            execute=args.execute,
            send=args.send or args.send_only,
            send_only=args.send_only,
            export_dir=args.export_pending,
        )
    )
    print(json.dumps(result))
    if result.get("retrieval_failed") or result.get("email", {}).get("uncertain"):
        sys.exit(1)
