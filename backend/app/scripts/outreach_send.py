"""Send today's invitation emails (systemd timer vidhisangh-outreach, daily).

    python -m app.scripts.outreach_send            # send, spaced 10-30 s apart
    python -m app.scripts.outreach_send --dry-run  # show what would go out

Does nothing while sending is paused in Platform admin → Outreach, or until the
invitation mail service (VS_OUTREACH_SMTP_*) is configured.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import session_scope
from app.core.outreach_mail import get_outreach_sender
from app.modules.outreach import service
from app.modules.outreach.models import OutreachContact, OutreachStatus


async def run(dry_run: bool) -> dict:
    async with session_scope(bypass_rls=True) as session:
        cfg = await service.get_settings(session)
        await session.commit()
        if dry_run:
            focus = await service.active_focus(session, cfg.focus)
            where = [OutreachContact.status == OutreachStatus.QUEUED, *service.focus_where(focus)]
            queued = (await session.scalars(select(OutreachContact.email).where(*where)
                                            .order_by(*service.pick_order(focus)).limit(cfg.daily_limit))).all()
            due = await service.reminder_candidates(session, datetime.now(UTC), 5000)
            return {"paused": cfg.paused, "daily_limit": cfg.daily_limit, "focus": cfg.focus,
                    "active_focus": await service.active_focus(session, cfg.focus), "reminders_due": len(due), "reminders_per_day": max(1, cfg.daily_limit // service.REMINDER_SHARE),
                    "queued_in_focus": await service.queued_count(session, focus=focus),
                    "sent_today": await service.sent_today(session), "next": list(queued)}
        sender = get_outreach_sender()
        if sender is None:
            return {"skipped": "VS_OUTREACH_SMTP_HOST is not set"}
        pause = lambda: asyncio.sleep(random.uniform(10, 30))  # noqa: E731
        # Reminders first (an opened invitation is warmer than a cold one), then today's new invitations,
        # both within the same daily number.
        reminders = await service.send_reminders(session, sender, pause=pause)
        invitations = await service.send_batch(session, sender, pause=pause)
        return {"reminders": reminders, "invitations": invitations}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    print(asyncio.run(run(parser.parse_args().dry_run)))
