"""Pluggable transport for outbound webhook delivery.

Abstracts the HTTP POST so delivery is testable without hitting the network,
mirroring the ``storage`` / ``payments`` / ``channels`` seams. Tests swap in a
``RecordingTransport`` (via :func:`set_webhook_transport`) so no real request
leaves the process.

Security (audit A-3): the real transport never follows redirects, re-validates
the receiver URL right before every send and connects to the vetted IP (see
``app.core.link_preview.assert_public_http_url``), uses a hard timeout, and
returns only the status code — the response body is never read into the
delivery log.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from app.core.link_preview import assert_public_http_url, http_client

DELIVERY_TIMEOUT_SECONDS = 10.0


@runtime_checkable
class WebhookTransport(Protocol):
    async def send(self, url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
        """POST ``body`` to ``url``; return ``(status_code, short_reason)``.

        ``short_reason`` must never contain the receiver's response body."""
        ...


class HttpxTransport:
    """Real HTTP delivery (production/dev default)."""

    async def send(self, url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
        # Re-resolve and re-check immediately before connecting, then pin the
        # connection to that address (defeats DNS rebinding between create and send).
        pinned = await assert_public_http_url(url)
        async with http_client(
            timeout=httpx.Timeout(DELIVERY_TIMEOUT_SECONDS), follow_redirects=False
        ) as client:
            resp = await client.post(
                pinned.pinned_url,
                content=body,
                headers={**headers, **pinned.headers},
                extensions=pinned.extensions,
            )
            await resp.aclose()  # never buffer/store the receiver's body
            return resp.status_code, ""


class RecordingTransport:
    """In-process transport used by tests: records calls, always succeeds
    (or fails ``fail_times`` times first, for retry/circuit-breaker tests)."""

    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict[str, object]] = []
        self.fail_times = 0
        self.raise_exc: Exception | None = None

    async def send(self, url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
        self.calls.append({"url": url, "headers": headers, "body": body})
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.fail_times > 0:
            self.fail_times -= 1
            return 500, ""
        return self.status_code, ""


_transport: WebhookTransport | None = None


def get_webhook_transport() -> WebhookTransport:
    global _transport
    if _transport is None:
        _transport = HttpxTransport()
    return _transport


def set_webhook_transport(transport: WebhookTransport | None) -> None:
    """Override the process-wide transport (tests). ``None`` restores the default."""
    global _transport
    _transport = transport
