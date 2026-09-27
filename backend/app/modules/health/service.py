"""System diagnostics for the admin dashboard.

Aggregates app metadata, dependency connectivity, the applied migration
revision, and the configuration status of optional integrations — **without
ever exposing secret values** (only whether each integration is wired).
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.channels import LogProvider, get_channels
from app.core.config import settings
from app.core.redis import ping_redis
from app.modules.notifications.models import NotificationChannel

_REDIS_TIMEOUT_S = 2.0


class SystemInfoService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def overview(self) -> dict:
        return {
            "app": {
                "name": settings.PROJECT_NAME,
                "version": __version__,
                "environment": settings.ENVIRONMENT.value,
            },
            "migration": await self._migration_revision(),
            "checks": [await self._db_check(), await self._redis_check()],
            "integrations": self._integrations(),
            "channels": self._channels(),
        }

    # ─── Dependency checks ──────────────────────────────────────────
    async def _db_check(self) -> dict:
        try:
            await self.session.execute(text("SELECT 1"))
            return {"name": "database", "status": "ok", "detail": None}
        except Exception as exc:  # noqa: BLE001
            return {"name": "database", "status": "error", "detail": exc.__class__.__name__}

    async def _redis_check(self) -> dict:
        try:
            await asyncio.wait_for(ping_redis(), timeout=_REDIS_TIMEOUT_S)
            return {"name": "redis", "status": "ok", "detail": None}
        except Exception as exc:  # noqa: BLE001
            return {"name": "redis", "status": "unreachable", "detail": exc.__class__.__name__}

    async def _migration_revision(self) -> str | None:
        """The applied Alembic head. Absent when the schema was created directly
        from metadata (e.g. the SQLite test DB) — reported as ``None``."""
        try:
            res = await self.session.execute(text("SELECT version_num FROM alembic_version"))
            return res.scalar_one_or_none()
        except Exception:  # noqa: BLE001
            return None

    # ─── Configuration (booleans only, never secrets) ───────────────
    def _integrations(self) -> list[dict]:
        razorpay = bool(os.environ.get("VS_RAZORPAY_KEY_ID") and os.environ.get("VS_RAZORPAY_KEY_SECRET"))
        return [
            {"name": "Email (SMTP)", "key": "email",
             "status": "live" if settings.SMTP_HOST else "log-fallback"},
            {"name": "Slack", "key": "slack",
             "status": "live" if os.environ.get("VS_SLACK_WEBHOOK") else "log-fallback"},
            {"name": "Payments (Razorpay)", "key": "razorpay",
             "status": "live" if razorpay else "mock"},
            {"name": "Object storage", "key": "storage",
             "status": os.environ.get("VS_STORAGE_BACKEND", "local").lower()},
        ]

    def _channels(self) -> list[dict]:
        registry = get_channels()
        result: list[dict] = [
            {"channel": NotificationChannel.IN_APP.value, "provider": "in_app", "status": "live"}
        ]
        for channel in NotificationChannel:
            if channel == NotificationChannel.IN_APP:
                continue
            provider = registry.provider_for(channel)
            if provider is None:
                result.append({"channel": channel.value, "provider": "-", "status": "not_configured"})
            elif isinstance(provider, LogProvider):
                result.append({"channel": channel.value, "provider": "log", "status": "log-fallback"})
            else:
                status = "live" if provider.configured else "not_configured"
                result.append({"channel": channel.value, "provider": provider.name, "status": status})
        return result
