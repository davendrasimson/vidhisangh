"""Pluggable transport for outbound webhook delivery.

Abstracts the HTTP POST so delivery is testable without hitting the network,
mirroring the ``storage`` / ``payments`` / ``channels`` seams. Tests swap in a
``RecordingTransport`` (via :func:`set_webhook_transport`) so no real request
leaves the process.

NOTE: deliveries currently happen inline within the emitting request, guarded by
try/except. Moving fan-out onto an async queue (Celery/Redis) with retries and
backoff is the production hardening step and is deliberately deferred.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx


@runtime_checkable
class WebhookTransport(Protocol):
    async def send(self, url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
        """POST ``body`` to ``url``; return ``(status_code, response_snippet)``."""
        ...


class HttpxTransport:
    """Real HTTP delivery (production/dev default)."""

    async def send(self, url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, content=body, headers=headers)
            return resp.status_code, resp.text[:500]


class RecordingTransport:
    """In-process transport used by tests: records calls, always succeeds."""

    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict[str, object]] = []

    async def send(self, url: str, headers: dict[str, str], body: bytes) -> tuple[int, str]:
        self.calls.append({"url": url, "headers": headers, "body": body})
        return self.status_code, "ok"


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
