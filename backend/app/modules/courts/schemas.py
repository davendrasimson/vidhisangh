from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class CauseListLink(BaseModel):
    label: str
    url: str


class CauseListDay(BaseModel):
    for_date: date
    lists: list[CauseListLink]
    fetched_at: datetime


class CourtCard(BaseModel):
    """The member's court on the Daily page: public details and the cause lists
    published for today and the next listing day."""

    slug: str
    name: str
    website: str
    cause_list_url: str
    ecourts_url: str | None = None   # the eCourts High Court services page (every High Court)
    group_id: uuid.UUID | None = None  # the official group for this court
    fetches: bool                     # whether VidhiSangh reads this court's index
    today: CauseListDay | None = None
    next: CauseListDay | None = None
