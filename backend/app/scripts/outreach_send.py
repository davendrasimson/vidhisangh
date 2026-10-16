"""Send today's invitation emails (systemd timer vidhisangh-outreach, daily).

    python -m app.scripts.outreach_send            # send, spaced 30-90 s apart
    python -m app.scripts.outreach_send --dry-run  # show what would go out

Does nothing while sending is paused in Platform admin → Outreach, or until the
invitation mail service (VS_OUTREACH_SMTP_*) is configured.
"""

from __future__ import annotations

import argparse
import asyncio
import random

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
            queued = (await session.scalars(select(OutreachContact.email).where(
                OutreachContact.status == OutreachStatus.QUEUED).order_by(OutreachContact.created_at).limit(cfg.daily_limit))).all()
            return {"paused": cfg.paused, "daily_limit": cfg.daily_limit,
                    "sent_today": await service.sent_today(session), "next": list(queued)}
        sender = get_outreach_sender()
        if sender is None:
            return {"skipped": "VS_OUTREACH_SMTP_HOST is not set"}
        return await service.send_batch(session, sender, pause=lambda: asyncio.sleep(random.uniform(30, 90)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    print(asyncio.run(run(parser.parse_args().dry_run)))
