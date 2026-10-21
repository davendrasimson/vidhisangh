"""Send tomorrow's hearing reminders (systemd timer vidhisangh-hearing-reminders).

    python -m app.scripts.hearing_reminders            # send
    python -m app.scripts.hearing_reminders --dry-run  # counts only, nothing sent

WhatsApp to members who turned it on, push to members with the app (push
allowed); a channel that is not configured is skipped. Prints counts only:
no names, numbers or matters.
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import settings
from app.core.database import session_scope
from app.core.push import get_push_sender
from app.core.whatsapp import get_whatsapp_sender
from app.modules.notifications import hearing_reminders as reminders


async def run(dry_run: bool) -> dict:
    day = reminders.tomorrow_ist()
    async with session_scope(bypass_rls=True) as session:
        # One read with RLS bypassed (transaction-local); sending only writes
        # the global hearing_reminder_sends table.
        due = await reminders.collect(session, day)
        if dry_run:
            return {"day": day.isoformat(), "members": len(due), "hearings": sum(len(r.hearings) for r in due)}
        sender = get_whatsapp_sender() if settings.WA_REMINDER_TEMPLATE else None
        push = get_push_sender()
        if sender is None and push is None:
            return {"skipped": "neither WhatsApp nor push is configured", "members": len(due)}
        return {"day": day.isoformat(), **await reminders.send_reminders(session, sender, day, due, push=push)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    print(asyncio.run(run(parser.parse_args().dry_run)))
