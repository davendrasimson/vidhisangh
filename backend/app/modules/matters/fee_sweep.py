"""Daily fee sweep (systemd timer vidhisangh-fee-sweep), across every firm.

- A retainer raises a fee event at the start of each period (monthly, quarterly,
  half-yearly, yearly) counted from the arrangement's start, while the
  arrangement runs and the matter is not closed. The first period is raised
  when the arrangement is added; this raises the ones after it.
- A milestone due on a date falls due on that date, whether or not anyone
  opens the matter (opening it also fires it, see MatterService).

Idempotent: a period already raised (same arrangement and start date, even if
waived or invoiced) is never raised again, so a missed day is caught up later.
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.matters.models import (
    FeeEventKind,
    Matter,
    MatterFeeArrangement,
    MatterFeeEvent,
    MatterFeeMilestone,
    MatterStatus,
    MilestoneStatus,
    MilestoneTrigger,
    RetainerPeriod,
)

PERIOD_MONTHS = {
    RetainerPeriod.MONTHLY: 1, RetainerPeriod.QUARTERLY: 3,
    RetainerPeriod.HALF_YEARLY: 6, RetainerPeriod.YEARLY: 12,
}
# Payment terms on a retainer period, as for the first one.
RETAINER_DUE_DAYS = 7


def add_months(start: date, months: int) -> date:
    """Same day `months` later; the 31st becomes the last day of a shorter month."""
    month = start.month - 1 + months
    year, month = start.year + month // 12, month % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def period_starts(arr: MatterFeeArrangement, today: date) -> list[date]:
    """Every period start from the arrangement's start up to today (and its end)."""
    months = PERIOD_MONTHS.get(RetainerPeriod(arr.retainer_period)) if arr.retainer_period else None
    if not months:
        return []
    last = min(today, arr.effective_to) if arr.effective_to else today
    out, n = [], 0
    while (start := add_months(arr.effective_from, n * months)) <= last:
        out.append(start)
        n += 1
    return out


def _event(arr: MatterFeeArrangement, **fields) -> MatterFeeEvent:
    return MatterFeeEvent(
        tenant_id=arr.tenant_id, matter_id=arr.matter_id, arrangement_id=arr.id,
        currency=arr.currency, created_by=None, **fields,
    )


async def sweep(session: AsyncSession, today: date) -> dict[str, int]:
    """Raise due retainer periods, dated milestones and recurring-invoice copies. Caller commits."""
    live = (
        select(MatterFeeArrangement)
        .join(Matter, Matter.id == MatterFeeArrangement.matter_id)
        .where(
            MatterFeeArrangement.deleted_at.is_(None),
            MatterFeeArrangement.effective_from <= today,
            Matter.deleted_at.is_(None),
            Matter.status != MatterStatus.CLOSED,
        )
    )

    retainers = 0
    for arr in (await session.scalars(live.where(
        MatterFeeArrangement.retainer_amount.is_not(None), MatterFeeArrangement.retainer_period.is_not(None),
    ))).all():
        raised = set((await session.scalars(select(MatterFeeEvent.occurred_on).where(
            MatterFeeEvent.arrangement_id == arr.id, MatterFeeEvent.kind == FeeEventKind.RETAINER,
            MatterFeeEvent.deleted_at.is_(None),
        ))).all())
        for start in period_starts(arr, today):
            if start in raised:
                continue
            session.add(_event(
                arr, kind=FeeEventKind.RETAINER, amount=Decimal(arr.retainer_amount),
                description=f"Retainer — {str(arr.retainer_period).replace('_', ' ')} period from {start:%d/%m/%Y}",
                occurred_on=start, due_on=start + timedelta(days=RETAINER_DUE_DAYS),
            ))
            retainers += 1

    milestones = 0
    from app.modules.matters.service import MatterService
    rows = (await session.execute(
        select(MatterFeeMilestone, MatterFeeArrangement)
        .join(MatterFeeArrangement, MatterFeeArrangement.id == MatterFeeMilestone.arrangement_id)
        .join(Matter, Matter.id == MatterFeeArrangement.matter_id)
        .where(
            MatterFeeMilestone.trigger == MilestoneTrigger.ON_DATE,
            MatterFeeMilestone.status == MilestoneStatus.PENDING,
            MatterFeeMilestone.due_on.is_not(None), MatterFeeMilestone.due_on <= today,
            MatterFeeMilestone.deleted_at.is_(None),
            MatterFeeArrangement.deleted_at.is_(None),
            (MatterFeeArrangement.effective_to.is_(None)) | (MatterFeeArrangement.effective_to >= today),
            Matter.deleted_at.is_(None), Matter.status != MatterStatus.CLOSED,
        )
    )).all()
    for ms, arr in rows:
        ms.status, ms.triggered_at = MilestoneStatus.DUE, datetime.now(UTC)
        session.add(_event(
            arr, milestone_id=ms.id, kind=FeeEventKind.MILESTONE, description=ms.label[:300],
            amount=MatterService._milestone_amount(arr, ms) or Decimal(0),
            occurred_on=today, due_on=today + timedelta(days=ms.due_days),
        ))
        milestones += 1

    await session.flush()
    from app.modules.billing.recurring import raise_due   # billing imports matters; resolve late
    recurring = await raise_due(session, today)
    return {"retainer_periods": retainers, "dated_milestones": milestones, "recurring_invoices": recurring}
