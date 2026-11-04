"""Send VidhiSangh Daily (systemd timer vidhisangh-daily-brief, 07:30 IST Mon-Sat).

    python -m app.scripts.daily_brief            # post today's official items if not yet posted, then
                                                 # push to members with the app and send the WhatsApp
                                                 # template to members who said yes to it
    python -m app.scripts.daily_brief --dry-run  # what today's message would say and to how many; nothing written or sent

Each channel is skipped (and says so) when it is not configured: push needs
VS_FCM_CREDENTIALS_FILE, WhatsApp the number's token and VS_WA_DAILY_TEMPLATE.
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import settings
from app.core.database import session_scope
from app.core.push import get_push_sender
from app.core.whatsapp import get_whatsapp_sender
from app.modules.brief import service


async def run(dry_run: bool) -> dict:
    day = service.today_ist()
    report: dict = {"day": day.isoformat(), "lead": service.lead_for(day), "pushes": service.pushes_on(day)}
    async with session_scope(bypass_rls=True) as session:
        if dry_run:
            brief = await service.compose(session, day, None)
            report["members_with_app"] = len(await service.recipients(session))
            report["whatsapp_opted_in"] = len(await service.whatsapp_recipients(session))
            report["message"] = service._message(service.lead_for(day), brief, {"joined_7d": 0, "in_city": 0, "city": None})
            return report
        push = get_push_sender()
        if push is None:
            report["push"] = "skipped: push is not configured (VS_FCM_CREDENTIALS_FILE)"
            await service.post_daily(session)  # the official items still go up on time
        else:
            report["push"] = await service.send_briefs(session, push, day)
        whatsapp = get_whatsapp_sender()
        if whatsapp is None or not settings.WA_DAILY_TEMPLATE:
            report["whatsapp"] = "skipped: WhatsApp is not configured (token, VS_WA_PHONE_NUMBER_ID, VS_WA_DAILY_TEMPLATE)"
        else:
            report["whatsapp"] = await service.send_whatsapp_briefs(session, whatsapp, day)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    print(asyncio.run(run(parser.parse_args().dry_run)))
