"""Send the morning matter-board digest (systemd timer vidhisangh-board-digest).

    python -m app.scripts.matter_board_digest            # send
    python -m app.scripts.matter_board_digest --dry-run  # counts only, nothing sent

Push to members with the app (push allowed); WhatsApp only once
VS_WA_BOARD_DIGEST_TEMPLATE names an approved template. Prints counts only.
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import settings
from app.core.database import session_scope
from app.core.push import get_push_sender
from app.core.whatsapp import get_whatsapp_sender
from app.modules.matters import board_digest


async def run(dry_run: bool) -> dict:
    day = board_digest.today_ist()
    async with session_scope(bypass_rls=True) as session:
        due = await board_digest.collect(session, day)
        if dry_run:
            return {"day": day.isoformat(), "members": len(due), "matters": sum(len(d.items) for d in due)}
        sender = get_whatsapp_sender() if settings.WA_BOARD_DIGEST_TEMPLATE else None
        push = get_push_sender()
        if sender is None and push is None:
            return {"skipped": "neither WhatsApp nor push is configured", "members": len(due)}
        return {"day": day.isoformat(), **await board_digest.send_digests(session, sender, day, due, push=push)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    print(asyncio.run(run(parser.parse_args().dry_run)))
