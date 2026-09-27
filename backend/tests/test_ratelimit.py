"""Rate limiter scopes.

The limiter fails open without Redis (so the rest of the suite never sees a
429); here a tiny in-memory stand-in makes the counting observable. The point
under test: refresh has its own, generous bucket — sharing the credential
bucket let a hard refresh lock a whole NAT address out of the login page.
"""

from __future__ import annotations

import pytest
from fastapi import Request

from app.core import ratelimit
from app.core.exceptions import RateLimitError

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass

    async def ttl(self, key: str) -> int:
        return 7


def _request(ip: str = "203.0.113.9") -> Request:
    scope = {"type": "http", "headers": [(b"x-forwarded-for", ip.encode())], "client": (ip, 1234)}
    return Request(scope)


async def test_refresh_and_credentials_have_separate_buckets(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(ratelimit, "get_redis", lambda: fake)
    login = ratelimit.RateLimiter(times=10, window_seconds=60, scope="auth")
    refresh = ratelimit.RateLimiter(times=120, window_seconds=60, scope="refresh")

    # Ten credential attempts are allowed, the eleventh is not…
    for _ in range(10):
        await login(_request())
    with pytest.raises(RateLimitError) as exc:
        await login(_request())
    assert exc.value.details == {"retry_after": 7}
    assert "Try again in 7s" in str(exc.value.message)

    # …and that exhaustion does not touch refresh, which has 120 of its own.
    for _ in range(120):
        await refresh(_request())
    with pytest.raises(RateLimitError):
        await refresh(_request())

    # Another address is unaffected.
    await login(_request("198.51.100.4"))


async def test_configured_limiters_use_distinct_scopes() -> None:
    assert ratelimit.auth_rate_limit.scope != ratelimit.refresh_rate_limit.scope
    assert ratelimit.refresh_rate_limit.times >= 10 * ratelimit.auth_rate_limit.times


async def test_limiter_fails_open_without_redis(monkeypatch) -> None:
    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(ratelimit, "get_redis", boom)
    limiter = ratelimit.RateLimiter(times=1, window_seconds=60, scope="x")
    for _ in range(5):  # never raises — an outage must not block sign-in
        await limiter(_request())
