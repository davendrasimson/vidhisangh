"""Redis-backed fixed-window rate limiting.

Exposed as FastAPI dependencies. Fails **open** (allows the request) if Redis
is unavailable so a cache outage never takes down authentication — an outage is
logged instead. Limits are keyed by client IP + route.
"""

from __future__ import annotations

import structlog
from fastapi import Request

from app.core.config import settings
from app.core.exceptions import RateLimitError
from app.core.redis import get_redis

log = structlog.get_logger("app.ratelimit")


class RateLimiter:
    def __init__(self, *, times: int, window_seconds: int, scope: str) -> None:
        self.times = times
        self.window = window_seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        key = f"rl:{self.scope}:{ip}"
        try:
            redis = get_redis()
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, self.window)
            if current > self.times:
                ttl = await redis.ttl(key)
                raise RateLimitError(
                    f"Rate limit exceeded. Try again in {max(ttl, 1)}s.",
                    details={"retry_after": max(ttl, 1)},
                )
        except RateLimitError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail open on cache errors
            log.warning("ratelimit_unavailable", error=str(exc))


# Pre-configured limiters.
auth_rate_limit = RateLimiter(
    times=settings.AUTH_RATE_LIMIT_PER_MINUTE, window_seconds=60, scope="auth"
)
# Refresh has its own, generous bucket. Sharing the credential bucket meant a
# hard refresh (one refresh call per tab) could lock a whole office — one NAT
# address — out of the login page for a minute.
refresh_rate_limit = RateLimiter(
    times=settings.REFRESH_RATE_LIMIT_PER_MINUTE, window_seconds=60, scope="refresh"
)
default_rate_limit = RateLimiter(
    times=settings.RATE_LIMIT_PER_MINUTE, window_seconds=60, scope="default"
)
