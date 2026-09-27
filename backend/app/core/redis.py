"""Async Redis client (cache, rate limiting, ephemeral tokens).

A single lazily-created connection pool is shared across the app. Used by the
rate limiter and for short-lived artifacts such as OTP/MFA challenge state.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return the shared Redis client, creating the pool on first use."""
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
    return _client


async def ping_redis() -> bool:
    return bool(await get_redis().ping())


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
