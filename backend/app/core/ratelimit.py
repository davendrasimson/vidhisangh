"""Redis-backed fixed-window rate limiting.

Exposed as FastAPI dependencies. Buckets are keyed by *scope* plus a subject:

- :class:`RateLimiter` — per client IP (behind trusted proxies, see
  :func:`app.core.deps.client_ip`).
- :class:`AccountRateLimiter` — per account (lower-cased ``email`` in the JSON
  body), so a distributed password-guess against one mailbox is throttled even
  when every attempt comes from a different address.
- :class:`UserRateLimiter` — per authenticated user (falls back to IP).

Failure mode (audit A-2): limiters guarding credentials (``fail_closed=True``)
answer **503 + Retry-After** when Redis is unreachable, so an outage can never
mean "unlimited guesses". Everything else fails open, logs, and increments the
``vs_ratelimit_fallback_total`` Prometheus counter so the outage is visible.

``RATE_LIMITING_ENABLED=false`` turns every limiter into a no-op (test suite
only; production refuses that setting).
"""

from __future__ import annotations

import structlog
from fastapi import Request
from starlette.requests import HTTPConnection
from prometheus_client import Counter

from app.core.config import settings
from app.core.deps import CurrentUserDep, client_ip
from app.core.exceptions import AppError, RateLimitError
from app.core.redis import get_redis

log = structlog.get_logger("app.ratelimit")

RATELIMIT_FALLBACK = Counter(
    "vs_ratelimit_fallback_total",
    "Rate-limit checks that fell back (open or closed) because Redis was unavailable.",
    ["scope", "mode"],
)


class RateLimiterUnavailableError(AppError):
    status_code = 503
    code = "rate_limiter_unavailable"
    message = "Sign-in is temporarily unavailable. Please try again shortly."


class RateLimiter:
    def __init__(
        self, *, times: int, window_seconds: int, scope: str, fail_closed: bool = False
    ) -> None:
        self.times = times
        self.window = window_seconds
        self.scope = scope
        self.fail_closed = fail_closed

    async def check(self, subject: str | None) -> None:
        """Count one hit for ``subject`` in this scope; raise when over the limit."""
        if not settings.RATE_LIMITING_ENABLED:
            return
        key = f"rl:{self.scope}:{subject or 'unknown'}"
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
        except Exception as exc:  # noqa: BLE001 - cache outage
            mode = "closed" if self.fail_closed else "open"
            RATELIMIT_FALLBACK.labels(scope=self.scope, mode=mode).inc()
            log.warning("ratelimit_unavailable", scope=self.scope, mode=mode, error=str(exc))
            if self.fail_closed:
                raise RateLimiterUnavailableError(
                    details={"retry_after": 30}
                ) from exc

    async def __call__(self, request: HTTPConnection) -> None:
        # HTTPConnection covers both Request and WebSocket: the router-wide
        # default limiter also runs on the /ws handshake.
        await self.check(client_ip(request))


class AccountRateLimiter(RateLimiter):
    """Keyed by the lower-cased ``email`` in the JSON body (login, MFA, reset)."""

    async def __call__(self, request: Request) -> None:  # type: ignore[override]
        email = await self._email(request)
        if email:
            await self.check(f"acct:{email}")

    @staticmethod
    async def _email(request: Request) -> str | None:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - not JSON / empty → the endpoint will 422
            return None
        if isinstance(body, dict):
            email = body.get("email")
            if isinstance(email, str) and email.strip():
                return email.strip().lower()[:320]
        return None


class UserRateLimiter(RateLimiter):
    """Keyed by the authenticated user id (IP when unauthenticated)."""

    async def __call__(self, request: Request, current: CurrentUserDep) -> None:  # type: ignore[override]
        await self.check(f"user:{current.id}" if current else client_ip(request))


# Pre-configured limiters.
auth_rate_limit = RateLimiter(
    times=settings.AUTH_RATE_LIMIT_PER_MINUTE, window_seconds=60, scope="auth", fail_closed=True
)
# Same credential attempts, counted per account instead of per address.
account_rate_limit = AccountRateLimiter(
    times=settings.AUTH_ACCOUNT_RATE_LIMIT_PER_MINUTE,
    window_seconds=60,
    scope="auth-account",
    fail_closed=True,
)
# New organisations per IP — tight, because the 409 on an existing address is an
# enumeration oracle the product has chosen to keep (see the audit report).
register_rate_limit = RateLimiter(
    times=settings.REGISTER_RATE_LIMIT_PER_MINUTE, window_seconds=60, scope="register", fail_closed=True
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
# /auth/mfa/* — per user (TOTP guesses against one's own second factor).
mfa_rate_limit = UserRateLimiter(
    times=settings.MFA_RATE_LIMIT_PER_MINUTE, window_seconds=60, scope="mfa", fail_closed=True
)
# Public, token-authenticated routes (client portal, KYC form) — per IP.
public_token_rate_limit = RateLimiter(
    times=settings.PUBLIC_TOKEN_RATE_LIMIT_PER_MINUTE, window_seconds=60, scope="public-token"
)
# Per-user buckets for expensive/abusable authenticated routes.
link_preview_rate_limit = UserRateLimiter(
    times=settings.LINK_PREVIEW_RATE_LIMIT_PER_MINUTE, window_seconds=60, scope="link-preview"
)
upload_rate_limit = UserRateLimiter(
    times=settings.UPLOAD_RATE_LIMIT_PER_MINUTE, window_seconds=60, scope="upload"
)
# WebSocket handshakes per IP (checked by hand in ws.py — no Request there).
ws_handshake_rate_limit = RateLimiter(
    times=settings.WS_HANDSHAKE_RATE_LIMIT_PER_MINUTE, window_seconds=60, scope="ws"
)
