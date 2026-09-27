"""Response schemas for the analytics dashboards.

Money is emitted as ``float`` (rounded to paise) rather than ``Decimal``: these
are display aggregates, not amounts of record, so a plain JSON number keeps the
frontend charting math trivial.
"""

from __future__ import annotations

from pydantic import BaseModel


class Bucket(BaseModel):
    """A grouped count (and optional monetary total) keyed by an enum value."""

    key: str
    count: int
    amount: float = 0.0


class RevenueSummary(BaseModel):
    total_invoiced: float
    total_collected: float
    outstanding: float
    overdue_amount: float
    invoice_count: int
    by_status: list[Bucket]


class MattersSummary(BaseModel):
    total: int
    open: int
    by_status: list[Bucket]
    by_type: list[Bucket]
    by_stage: list[Bucket]


class PipelineSummary(BaseModel):
    total_leads: int
    open_value: float
    won_value: float
    won_count: int
    lost_count: int
    conversion_rate: float  # won / (won + lost), 0..1
    by_status: list[Bucket]


class ProductivitySummary(BaseModel):
    open_tasks: int
    overdue_tasks: int
    upcoming_hearings: int  # scheduled, next 30 days
    hearings_next_7d: int


class TrendPoint(BaseModel):
    month: str  # "YYYY-MM"
    invoiced: float
    collected: float


class AnalyticsOverview(BaseModel):
    revenue: RevenueSummary
    matters: MattersSummary
    pipeline: PipelineSummary
    productivity: ProductivitySummary
    revenue_trend: list[TrendPoint]
