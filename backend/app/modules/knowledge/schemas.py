"""Pydantic schemas for the knowledge base module."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from pydantic_core import PydanticCustomError

from app.modules.knowledge.models import KnowledgeCategory


class KnowledgeResources(BaseModel):
    source_url: HttpUrl | None = Field(default=None, max_length=2000)
    reviewed_on: date | None = None
    attachments: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    @field_validator("reviewed_on")
    @classmethod
    def review_not_in_future(cls, value: date | None) -> date | None:
        if value and value > date.today():
            raise PydanticCustomError("future_review", "Review date cannot be in the future.")
        return value


class KnowledgeCreate(KnowledgeResources):
    title: str = Field(min_length=2, max_length=300)
    category: KnowledgeCategory = KnowledgeCategory.NOTE
    body: str = Field(min_length=1, max_length=100000)
    practice_area: str | None = Field(default=None, max_length=150)
    tags: list[str] = Field(default_factory=list, max_length=20)


class KnowledgeUpdate(KnowledgeResources):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    category: KnowledgeCategory | None = None
    body: str | None = Field(default=None, min_length=1, max_length=100000)
    practice_area: str | None = Field(default=None, max_length=150)
    tags: list[str] | None = Field(default=None, max_length=20)


class KnowledgeRead(KnowledgeResources):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    category: KnowledgeCategory
    body: str
    practice_area: str | None
    tags: list[str]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class KnowledgeSummary(BaseModel):
    """Lighter shape for list/search results (no body)."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    category: KnowledgeCategory
    practice_area: str | None
    tags: list[str]
    updated_at: datetime
