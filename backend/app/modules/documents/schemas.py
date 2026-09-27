"""Pydantic schemas for the documents module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.http_utils import sanitize_filename


def _clean_name(value: str | None) -> str | None:
    """Strip quotes, backslashes, semicolons, path separators and control
    characters from a user-supplied name so it can never break a
    ``Content-Disposition`` header or a storage path."""
    if value is None:
        return None
    cleaned = sanitize_filename(value)
    if cleaned == "untitled" and value.strip() not in ("", "untitled"):
        raise ValueError("Name contains no usable characters.")
    return cleaned


# ─── Folders ────────────────────────────────────────────────────────
class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    _clean = field_validator("name")(_clean_name)
    parent_id: uuid.UUID | None = None
    matter_id: uuid.UUID | None = None


class FolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    matter_id: uuid.UUID | None
    created_at: datetime


# ─── Documents ──────────────────────────────────────────────────────
class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    folder_id: uuid.UUID | None
    matter_id: uuid.UUID | None
    client_id: uuid.UUID | None = None
    client_name: str | None = None
    content_type: str
    size: int
    tags: list[str]
    current_version_id: uuid.UUID | None
    version_count: int
    locked_by: uuid.UUID | None
    locked_at: datetime | None
    uploaded_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class DocumentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    folder_id: uuid.UUID | None = None
    # Explicit null unlinks the client; absent leaves it alone.
    client_id: uuid.UUID | None = None
    tags: list[str] | None = Field(default=None, max_length=30)

    _clean = field_validator("name")(_clean_name)


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    document_id: uuid.UUID
    version_no: int
    size: int
    content_type: str
    checksum: str
    comment: str | None
    uploaded_by: uuid.UUID
    created_at: datetime
