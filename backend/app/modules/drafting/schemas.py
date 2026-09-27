"""Pydantic schemas for drafting."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.drafting.models import DEFAULT_PAGE, DraftStatus

# A draft is text; 8 MB of JSON is a very long document with pasted images.
_MAX_CONTENT_BYTES = 8 * 1024 * 1024
_PAGE_SIZES = {"A4", "Letter", "Legal"}


class PageMargins(BaseModel):
    top: float = Field(25.4, ge=0, le=80)
    right: float = Field(25.4, ge=0, le=80)
    bottom: float = Field(25.4, ge=0, le=80)
    left: float = Field(25.4, ge=0, le=80)


class PageSettings(BaseModel):
    size: str = "A4"
    orientation: str = "portrait"
    margins: PageMargins = Field(default_factory=PageMargins)

    @field_validator("size")
    @classmethod
    def _size(cls, v: str) -> str:
        if v not in _PAGE_SIZES:
            raise ValueError(f"size must be one of {sorted(_PAGE_SIZES)}")
        return v

    @field_validator("orientation")
    @classmethod
    def _orientation(cls, v: str) -> str:
        if v not in ("portrait", "landscape"):
            raise ValueError("orientation must be portrait or landscape")
        return v


def _check_size(value: Any) -> Any:
    """Cap a content field (JSON or HTML) at 8 MB, measured as serialised bytes."""
    import json

    if value is None:
        return value
    size = len(value.encode("utf-8")) if isinstance(value, str) else len(json.dumps(value))
    if size > _MAX_CONTENT_BYTES:
        raise ValueError("Document is too large (8 MB limit).")
    return value


class DraftCreate(BaseModel):
    title: str = Field(default="Untitled document", min_length=1, max_length=300)
    language: str = Field(default="en", max_length=5)
    template_id: str | None = Field(default=None, max_length=80)
    matter_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    content_json: dict = Field(default_factory=lambda: {"type": "doc", "content": [{"type": "paragraph"}]})
    content_html: str = ""
    page: PageSettings = Field(default_factory=PageSettings)

    _size = field_validator("content_json", "content_html")(_check_size)


class DraftUpdate(BaseModel):
    """Autosave payload — every field optional; only what changed is sent."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    language: str | None = Field(default=None, max_length=5)
    matter_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    status: DraftStatus | None = None
    content_json: dict | None = None
    content_html: str | None = None
    page: PageSettings | None = None

    _size = field_validator("content_json", "content_html")(_check_size)


class DraftSummary(BaseModel):
    """List row — no content."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    language: str
    template_id: str | None
    matter_id: uuid.UUID | None
    client_id: uuid.UUID | None = None
    client_name: str | None = None
    status: DraftStatus
    word_count: int
    version_count: int
    library_document_id: uuid.UUID | None
    created_by: uuid.UUID
    updated_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class DraftRead(DraftSummary):
    content_json: dict
    content_html: str
    page: dict = Field(default_factory=lambda: dict(DEFAULT_PAGE))


class DraftVersionCreate(BaseModel):
    note: str | None = Field(default=None, max_length=300)


class DraftVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version_no: int
    note: str | None
    word_count: int
    created_by: uuid.UUID
    created_at: datetime


class DraftVersionDetail(DraftVersionRead):
    content_json: dict
    content_html: str


class FileToLibrary(BaseModel):
    folder_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=500)
