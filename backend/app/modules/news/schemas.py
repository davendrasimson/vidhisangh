"""Pydantic schemas for the legal news module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.news.models import NewsCategory


class NewsItemCreate(BaseModel):
    title: str = Field(min_length=2, max_length=400)
    summary: str | None = Field(default=None, max_length=20000)
    source: str = Field(min_length=1, max_length=150)
    category: NewsCategory = NewsCategory.NEWS
    url: str | None = Field(default=None, max_length=600)
    published_at: datetime
    tags: list[str] = Field(default_factory=list, max_length=20)


class NewsItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    summary: str | None
    source: str
    category: NewsCategory
    url: str | None
    image_url: str | None = None
    published_at: datetime
    tags: list[str]
