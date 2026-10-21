"""``POST /funnel/{step}``: the site counts a sign-up step (no login needed).

Only known steps are accepted and each address may count a few a minute, so
the totals cannot be inflated in bulk. Nothing about the visitor is stored.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthSessionDep
from app.core.ratelimit import RateLimiter
from app.modules.funnel.models import FunnelDaily

router = APIRouter(prefix="/funnel", tags=["Sign-up funnel"])
IST = ZoneInfo("Asia/Kolkata")
# In funnel order: home page seen → sign-up page → email form opened → WhatsApp code asked.
STEPS = ("landing_view", "register_view", "email_form_opened", "whatsapp_code_requested")
_limit = RateLimiter(times=20, window_seconds=60, scope="funnel", fail_closed=False)


async def count_step(session: AsyncSession, step: str, now: datetime | None = None) -> None:
    day = (now or datetime.now(UTC)).astimezone(IST).date()
    result = await session.execute(
        update(FunnelDaily).where(FunnelDaily.day == day, FunnelDaily.step == step)
        .values(count=FunnelDaily.count + 1).execution_options(synchronize_session=False)
    )
    if not result.rowcount:
        session.add(FunnelDaily(day=day, step=step, count=1))
    await session.flush()


@router.post("/{step}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False,
             dependencies=[Depends(_limit)])
async def record_step(step: str, session: AuthSessionDep) -> Response:
    if step in STEPS:
        await count_step(session, step)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def funnel_summary(session: AsyncSession, today: date, accounts_by_day: dict[date, int]) -> dict:
    """Totals per step for the last 7 and 30 days, with accounts created as the last step."""
    rows = (await session.execute(
        select(FunnelDaily.day, FunnelDaily.step, FunnelDaily.count).where(FunnelDaily.day > today - timedelta(days=30))
    )).all()

    def window(days: int) -> list[dict]:
        start = today - timedelta(days=days - 1)
        totals = {s: 0 for s in STEPS}
        for day, step, n in rows:
            if day >= start and step in totals:
                totals[step] += n
        totals["account_created"] = sum(n for d, n in accounts_by_day.items() if start <= d <= today)
        return [{"step": s, "count": totals[s]} for s in (*STEPS, "account_created")]

    first = min((d for d, _, _ in rows), default=None)
    return {"last_7_days": window(7), "last_30_days": window(30), "since": first.isoformat() if first else None}
