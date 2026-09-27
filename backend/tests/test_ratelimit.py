"""Rate limiter scopes, trusted-proxy addressing and failure modes (audit A-2).

The suite runs with ``RATE_LIMITING_ENABLED=false`` so the rest of the tests
never see a 429; here it is switched on per test with an in-memory Redis so
the counting is observable. Under test:

- refresh has its own, generous bucket (sharing the credential bucket let a
  hard refresh lock a whole NAT address out of the login page);
- ``X-Forwarded-For`` is only honoured from a trusted proxy, walked right to
  left (the first element used to be trusted blindly — a one-header bypass);
- per-account buckets throttle a distributed guess against one mailbox;
- credential limiters fail **closed** without Redis; the general limiter
  fails open and counts the fallback in Prometheus.
"""

from __future__ import annotations

import pytest
from fastapi import Request

from app.core import ratelimit
from app.core.config import settings
from app.core.deps import client_ip
from app.core.exceptions import RateLimitError
from tests.fake_redis import FakeRedis

pytestmark = pytest.mark.asyncio


def _request(
    ip: str = "203.0.113.9", *, forwarded: str | None = None, body: bytes = b""
) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    if body:
        headers.append((b"content-type", b"application/json"))
    scope = {"type": "http", "headers": headers, "client": (ip, 1234), "method": "POST", "path": "/"}
    chunks = [body]

    async def receive() -> dict:
        data = chunks.pop() if chunks else b""
        return {"type": "http.request", "body": data, "more_body": False}

    return Request(scope, receive)


@pytest.fixture
def limits_on(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(ratelimit, "get_redis", lambda: fake)
    monkeypatch.setattr(settings, "RATE_LIMITING_ENABLED", True)
    return fake


async def test_refresh_and_credentials_have_separate_buckets(limits_on) -> None:
    login = ratelimit.RateLimiter(times=10, window_seconds=60, scope="auth")
    refresh = ratelimit.RateLimiter(times=120, window_seconds=60, scope="refresh")

    # Ten credential attempts are allowed, the eleventh is not…
    for _ in range(10):
        await login(_request())
    with pytest.raises(RateLimitError) as exc:
        await login(_request())
    assert exc.value.details["retry_after"] >= 1
    assert "Try again in" in str(exc.value.message)

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
    assert ratelimit.auth_rate_limit.fail_closed and ratelimit.account_rate_limit.fail_closed
    assert not ratelimit.default_rate_limit.fail_closed


# ─── Trusted-proxy client address ───────────────────────────────────
async def test_forwarded_for_ignored_from_untrusted_peer(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "127.0.0.1,::1")
    # A client talking to us directly cannot pick its own address.
    assert client_ip(_request("203.0.113.9", forwarded="1.2.3.4")) == "203.0.113.9"


async def test_forwarded_for_walks_right_to_left_behind_trusted_proxy(monkeypatch) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "127.0.0.1,10.0.0.0/8")
    # nginx (127.0.0.1) appended the real client after whatever the client sent.
    assert client_ip(_request("127.0.0.1", forwarded="6.6.6.6, 203.0.113.9")) == "203.0.113.9"
    # Two trusted hops: skip both, take the rightmost untrusted address.
    assert client_ip(_request("127.0.0.1", forwarded="6.6.6.6, 203.0.113.9, 10.1.2.3")) == "203.0.113.9"
    # Header absent behind a proxy → the proxy's own address (never None).
    assert client_ip(_request("127.0.0.1")) == "127.0.0.1"


async def test_spoofed_header_cannot_reset_the_bucket(limits_on, monkeypatch) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "127.0.0.1")
    login = ratelimit.RateLimiter(times=3, window_seconds=60, scope="auth")
    for i in range(3):
        await login(_request("203.0.113.9", forwarded=f"10.0.0.{i}"))
    with pytest.raises(RateLimitError):  # the 4th, with yet another spoofed value
        await login(_request("203.0.113.9", forwarded="10.0.0.99"))


# ─── Per-account bucket ─────────────────────────────────────────────
async def test_account_bucket_throttles_one_mailbox_across_addresses(limits_on) -> None:
    per_account = ratelimit.AccountRateLimiter(times=2, window_seconds=60, scope="auth-account")
    body = b'{"email": "Victim@Firm.co", "password": "x"}'
    await per_account(_request("1.1.1.1", body=body))
    await per_account(_request("2.2.2.2", body=body))
    with pytest.raises(RateLimitError):
        await per_account(_request("3.3.3.3", body=b'{"email": "victim@firm.co", "password": "y"}'))
    # A different account from the same addresses is untouched.
    await per_account(_request("3.3.3.3", body=b'{"email": "other@firm.co", "password": "y"}'))
    # No email in the body → nothing to key on, nothing counted.
    await per_account(_request("3.3.3.3", body=b'{"foo": 1}'))


# ─── Failure modes ──────────────────────────────────────────────────
async def test_general_limiter_fails_open_and_counts_fallback(monkeypatch) -> None:
    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(ratelimit, "get_redis", boom)
    monkeypatch.setattr(settings, "RATE_LIMITING_ENABLED", True)
    counter = ratelimit.RATELIMIT_FALLBACK.labels(scope="x", mode="open")
    before = counter._value.get()
    limiter = ratelimit.RateLimiter(times=1, window_seconds=60, scope="x")
    for _ in range(5):  # never raises — an outage must not block ordinary traffic
        await limiter(_request())
    assert counter._value.get() == before + 5


async def test_credential_limiter_fails_closed_without_redis(monkeypatch) -> None:
    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(ratelimit, "get_redis", boom)
    monkeypatch.setattr(settings, "RATE_LIMITING_ENABLED", True)
    limiter = ratelimit.RateLimiter(times=10, window_seconds=60, scope="auth", fail_closed=True)
    with pytest.raises(ratelimit.RateLimiterUnavailableError) as exc:
        await limiter(_request())
    assert exc.value.status_code == 503
    assert exc.value.details["retry_after"] > 0


async def test_master_switch_disables_counting(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(ratelimit, "get_redis", lambda: fake)
    monkeypatch.setattr(settings, "RATE_LIMITING_ENABLED", False)
    limiter = ratelimit.RateLimiter(times=1, window_seconds=60, scope="auth", fail_closed=True)
    for _ in range(3):
        await limiter(_request())
    assert fake.store == {}
