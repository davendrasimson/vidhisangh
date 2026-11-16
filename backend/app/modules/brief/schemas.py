from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.modules.courts.schemas import CourtCard
from app.modules.network.schemas import DailyCard, DirectoryPerson


class QuizStats(BaseModel):
    answers: int
    right: int


class QuizRead(BaseModel):
    id: str
    topic: str
    question: str
    options: list[str]
    link: str | None = None
    # Filled in once this member has answered (never before, so the page cannot leak the answer).
    chosen: int | None = None
    answer: int | None = None
    explanation: str | None = None
    stats: QuizStats


class OnThisDayRead(BaseModel):
    case: str
    decided: date
    citation: str | None = None
    holding: str
    judgment_id: uuid.UUID | None = None
    source: str  # curated | corpus
    basis: str | None = None  # corpus picks: ai (AI headnote) | scr (the SCR headnote)
    cited: int | None = None  # corpus picks: how often later judgments cite it (mined)


class FraternityRead(BaseModel):
    members: int
    in_city: int
    joined_7d: int
    city: str | None = None
    people: list[DirectoryPerson] = []


class BriefRead(BaseModel):
    day: date
    weekday: str
    lead: str  # section | judgment | quiz | on_this_day | news | fraternity
    section: DailyCard | None = None
    judgment: DailyCard | None = None
    news: list[DailyCard] = []
    quiz: QuizRead | None = None
    on_this_day: OnThisDayRead | None = None
    fraternity: FraternityRead | None = None
    court: CourtCard | None = None  # the member's court (from their profile) and its cause lists


class QuizAnswerIn(BaseModel):
    chosen: int = Field(ge=0, le=3)


class QuizAnswerRead(BaseModel):
    quiz_id: str
    chosen: int
    answer: int
    correct: bool
    explanation: str
    stats: QuizStats
    answered_at: datetime
