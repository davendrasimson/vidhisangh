"""Pydantic schemas for feature flags."""

from __future__ import annotations

from pydantic import BaseModel


class FlagRead(BaseModel):
    key: str
    name: str
    description: str
    enabled: bool
    default: bool
    overridden: bool  # true when the tenant has a stored override


class FlagUpdate(BaseModel):
    enabled: bool
