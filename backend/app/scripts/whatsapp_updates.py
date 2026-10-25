"""Send a product-update campaign on WhatsApp (approved marketing templates).

    python -m app.scripts.whatsapp_updates --campaign launch-2026-10-26 --dry-run
    python -m app.scripts.whatsapp_updates --campaign launch-2026-10-26
    python -m app.scripts.whatsapp_updates --campaign launch-2026-10-26 --owner-approved

Only members who said yes to product updates are sent to. ``--owner-approved``
also includes members who were never asked (the one-off launch send the owner
authorised on 25 Oct 2026); a "no" is always respected. Each number gets a
campaign once, even if the job is rerun. Prints counts only: no names or
numbers.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter

from app.core.database import session_scope
from app.core.whatsapp import get_whatsapp_sender
from app.modules.notifications import whatsapp_updates as updates


async def run(campaign: str, dry_run: bool, owner_approved: bool) -> dict:
    async with session_scope(bypass_rls=True) as session:
        # One read with RLS bypassed (transaction-local); sending only writes
        # the global whatsapp_campaign_sends table.
        recipients, skipped = await updates.collect(session, owner_approved=owner_approved)
        mix = Counter(f"{r.template}/{r.language}/{r.basis}" for r in recipients)
        summary = {"campaign": campaign, "numbers": len(recipients), "mix": dict(mix), "skipped": skipped}
        if dry_run:
            return summary
        sender = get_whatsapp_sender()
        if sender is None:
            return {**summary, "skipped_all": "WhatsApp is not configured"}
        return {**summary, **await updates.send_campaign(session, sender, campaign, recipients)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True, help="A name for this send, e.g. launch-2026-10-26")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--owner-approved", action="store_true",
                        help="Also send to members never asked (never to those who said no)")
    args = parser.parse_args()
    print(asyncio.run(run(args.campaign[:60], args.dry_run, args.owner_approved)))
