"""Push VidhiSangh Daily to members with the app (systemd timer vidhisangh-daily-brief, 07:30 IST Mon-Sat).

    python -m app.scripts.daily_brief            # post today's official items if not yet posted, then push
    python -m app.scripts.daily_brief --dry-run  # what today's message would say, nothing written or sent
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import session_scope
from app.core.push import get_push_sender
from app.modules.brief import service


async def run(dry_run: bool) -> dict:
    day = service.today_ist()
    async with session_scope(bypass_rls=True) as session:
        if dry_run:
            brief = await service.compose(session, day, None)
            members = await service.recipients(session)
            message = service._message(service.lead_for(day), brief, {"joined_7d": 0, "in_city": 0, "city": None})
            return {"day": day.isoformat(), "lead": service.lead_for(day), "pushes": service.pushes_on(day),
                    "members_with_app": len(members), "message": message}
        push = get_push_sender()
        if push is None:
            return {"day": day.isoformat(), "skipped": "push is not configured (VS_FCM_CREDENTIALS_FILE)"}
        return {"day": day.isoformat(), "lead": service.lead_for(day), **await service.send_briefs(session, push, day)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    print(asyncio.run(run(parser.parse_args().dry_run)))
