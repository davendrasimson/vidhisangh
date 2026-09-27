"""Schemas for the admin system-health & configuration dashboard."""

from __future__ import annotations

from pydantic import BaseModel


class AppInfo(BaseModel):
    name: str
    version: str
    environment: str


class Check(BaseModel):
    name: str
    status: str  # "ok" | "error" | "unreachable"
    detail: str | None = None


class Integration(BaseModel):
    name: str
    key: str
    status: str  # "live" | "log-fallback" | "mock" | "not_configured" | value


class ChannelStatus(BaseModel):
    channel: str
    provider: str
    status: str  # "live" | "log-fallback" | "not_configured"


class SystemOverview(BaseModel):
    app: AppInfo
    migration: str | None
    checks: list[Check]
    integrations: list[Integration]
    channels: list[ChannelStatus]
