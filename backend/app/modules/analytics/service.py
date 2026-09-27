"""Aggregation logic for the analytics dashboards.

All queries filter by ``tenant_id`` explicitly (alongside RLS) and skip
soft-deleted rows. Queries avoid dialect-specific date functions so the same
code runs on PostgreSQL (production) and SQLite (tests); month bucketing for
the revenue trend is done in Python.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.schemas import (
    AnalyticsOverview,
    Bucket,
    MattersSummary,
    PipelineSummary,
    ProductivitySummary,
    RevenueSummary,
    TrendPoint,
)
from app.modules.billing.models import Invoice, InvoiceStatus
from app.modules.crm.models import Lead, LeadStatus
from app.modules.matters.models import (
    Hearing,
    HearingStatus,
    Matter,
    MatterStatus,
    MatterTask,
    TaskStatus,
)

TREND_MONTHS = 6


def _f(value: object) -> float:
    """Coerce a possibly-``None`` Decimal/number aggregate to a rounded float."""
    return round(float(value or 0), 2)


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _recent_months(today: date, n: int) -> list[str]:
    """Return the last ``n`` month keys ending with ``today``'s month, in order."""
    keys: list[str] = []
    year, month = today.year, today.month
    for _ in range(n):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(keys))


class AnalyticsService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def overview(self, today: date) -> AnalyticsOverview:
        return AnalyticsOverview(
            revenue=await self._revenue(today),
            matters=await self._matters(),
            pipeline=await self._pipeline(),
            productivity=await self._productivity(today),
            revenue_trend=await self._revenue_trend(today),
        )

    # ─── Revenue ────────────────────────────────────────────────────
    async def _revenue(self, today: date) -> RevenueSummary:
        live = (
            Invoice.tenant_id == self.tenant_id,
            Invoice.deleted_at.is_(None),
            Invoice.status != InvoiceStatus.CANCELLED,
        )
        totals = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(Invoice.total), 0),
                    func.coalesce(func.sum(Invoice.amount_paid), 0),
                    func.count(),
                ).where(*live)
            )
        ).one()
        invoiced, collected, count = _f(totals[0]), _f(totals[1]), int(totals[2])

        outstanding = _f(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0)).where(
                        *live, Invoice.status.in_((InvoiceStatus.SENT, InvoiceStatus.OVERDUE))
                    )
                )
            ).scalar_one()
        )
        overdue = _f(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0)).where(
                        *live,
                        Invoice.status.in_((InvoiceStatus.SENT, InvoiceStatus.OVERDUE)),
                        Invoice.due_date.is_not(None),
                        Invoice.due_date < today,
                    )
                )
            ).scalar_one()
        )

        by_status = [
            Bucket(key=str(status), count=int(cnt), amount=_f(amt))
            for status, cnt, amt in (
                await self.session.execute(
                    select(Invoice.status, func.count(), func.coalesce(func.sum(Invoice.total), 0))
                    .where(Invoice.tenant_id == self.tenant_id, Invoice.deleted_at.is_(None))
                    .group_by(Invoice.status)
                )
            ).all()
        ]
        return RevenueSummary(
            total_invoiced=invoiced,
            total_collected=collected,
            outstanding=outstanding,
            overdue_amount=overdue,
            invoice_count=count,
            by_status=by_status,
        )

    # ─── Matters / caseload ─────────────────────────────────────────
    async def _matters(self) -> MattersSummary:
        base = (Matter.tenant_id == self.tenant_id, Matter.deleted_at.is_(None))

        async def grouped(column) -> list[Bucket]:
            rows = (
                await self.session.execute(
                    select(column, func.count()).where(*base).group_by(column)
                )
            ).all()
            return [Bucket(key=str(key), count=int(cnt)) for key, cnt in rows]

        total = int(
            (await self.session.execute(select(func.count()).where(*base))).scalar_one()
        )
        open_count = int(
            (
                await self.session.execute(
                    select(func.count()).where(*base, Matter.status == MatterStatus.OPEN)
                )
            ).scalar_one()
        )
        return MattersSummary(
            total=total,
            open=open_count,
            by_status=await grouped(Matter.status),
            by_type=await grouped(Matter.matter_type),
            by_stage=await grouped(Matter.stage),
        )

    # ─── CRM pipeline ───────────────────────────────────────────────
    async def _pipeline(self) -> PipelineSummary:
        base = (Lead.tenant_id == self.tenant_id, Lead.deleted_at.is_(None))
        rows = (
            await self.session.execute(
                select(
                    Lead.status, func.count(), func.coalesce(func.sum(Lead.estimated_value), 0)
                )
                .where(*base)
                .group_by(Lead.status)
            )
        ).all()

        by_status: list[Bucket] = []
        total = won_count = lost_count = 0
        open_value = won_value = 0.0
        for status, cnt, value in rows:
            cnt = int(cnt)
            total += cnt
            by_status.append(Bucket(key=str(status), count=cnt, amount=_f(value)))
            if status == LeadStatus.WON:
                won_count, won_value = cnt, _f(value)
            elif status == LeadStatus.LOST:
                lost_count = cnt
            else:
                open_value += _f(value)

        decided = won_count + lost_count
        return PipelineSummary(
            total_leads=total,
            open_value=round(open_value, 2),
            won_value=won_value,
            won_count=won_count,
            lost_count=lost_count,
            conversion_rate=round(won_count / decided, 4) if decided else 0.0,
            by_status=by_status,
        )

    # ─── Productivity ───────────────────────────────────────────────
    async def _productivity(self, today: date) -> ProductivitySummary:
        task_base = (
            MatterTask.tenant_id == self.tenant_id,
            MatterTask.deleted_at.is_(None),
            MatterTask.status == TaskStatus.OPEN,
        )
        open_tasks = int(
            (await self.session.execute(select(func.count()).where(*task_base))).scalar_one()
        )
        overdue_tasks = int(
            (
                await self.session.execute(
                    select(func.count()).where(
                        *task_base, MatterTask.due_on.is_not(None), MatterTask.due_on < today
                    )
                )
            ).scalar_one()
        )

        start = datetime.combine(today, time.min)

        async def hearings_within(days: int) -> int:
            return int(
                (
                    await self.session.execute(
                        select(func.count()).where(
                            Hearing.tenant_id == self.tenant_id,
                            Hearing.deleted_at.is_(None),
                            Hearing.status == HearingStatus.SCHEDULED,
                            Hearing.scheduled_on >= start,
                            Hearing.scheduled_on < start + timedelta(days=days),
                        )
                    )
                ).scalar_one()
            )

        return ProductivitySummary(
            open_tasks=open_tasks,
            overdue_tasks=overdue_tasks,
            upcoming_hearings=await hearings_within(30),
            hearings_next_7d=await hearings_within(7),
        )

    # ─── Revenue trend (monthly) ────────────────────────────────────
    async def _revenue_trend(self, today: date) -> list[TrendPoint]:
        months = _recent_months(today, TREND_MONTHS)
        window_start = date(int(months[0][:4]), int(months[0][5:7]), 1)
        buckets = {m: {"invoiced": 0.0, "collected": 0.0} for m in months}

        rows = (
            await self.session.execute(
                select(Invoice.issue_date, Invoice.total, Invoice.amount_paid).where(
                    Invoice.tenant_id == self.tenant_id,
                    Invoice.deleted_at.is_(None),
                    Invoice.status != InvoiceStatus.CANCELLED,
                    Invoice.issue_date.is_not(None),
                    Invoice.issue_date >= window_start,
                )
            )
        ).all()
        for issue_date, total, amount_paid in rows:
            key = _month_key(issue_date)
            if key in buckets:  # guard against a row dated in the current, partial month edge
                buckets[key]["invoiced"] += float(total or 0)
                buckets[key]["collected"] += float(amount_paid or 0)

        return [
            TrendPoint(month=m, invoiced=round(buckets[m]["invoiced"], 2), collected=round(buckets[m]["collected"], 2))
            for m in months
        ]
