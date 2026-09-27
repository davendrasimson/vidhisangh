"""Pluggable notification channels.

An abstraction over *how* a notification leaves the platform, mirroring the
``storage`` and ``payments`` seams. Each :class:`ChannelProvider` knows whether
it is ``configured`` (has the credentials/endpoint it needs) and how to
``send`` a :class:`ChannelMessage`.

Providers with live implementations:

- ``log``   — always configured; writes to the application log. The dev/test
              default so nothing external is required and routing is observable.
- ``email`` — SMTP; configured when ``VS_SMTP_HOST`` is set.
- ``slack`` — incoming webhook; configured when ``VS_SLACK_WEBHOOK`` is set.

Channels without a provider yet (``sms``/``whatsapp``/``push``/``teams``) resolve
to :data:`None`; the dispatcher records those routes as ``skipped`` until the
vendor infra is wired (see the deferred-infra items).

NOTE: sends currently happen inline within the caller's request. That is safe
for the ``log`` default (no I/O) and guarded by try/except for real providers;
moving fan-out onto an async queue (Celery/Redis) is the production hardening
step and is deliberately deferred.
"""

from __future__ import annotations

import hashlib
import logging
import os

from app.core.config import settings
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol, runtime_checkable

import httpx

from app.modules.notifications.models import NotificationChannel

logger = logging.getLogger("vidhisangh.notifications")


@dataclass(slots=True)
class ChannelMessage:
    to_email: str | None
    to_name: str | None
    subject: str
    body: str
    link: str | None = None


@runtime_checkable
class ChannelProvider(Protocol):
    name: str
    configured: bool

    async def send(self, message: ChannelMessage) -> None: ...


def address_ref(address: str | None) -> str:
    """A short, stable reference for a recipient address for log lines —
    ``sha256(lower(address))[:12]`` — so routing stays traceable without the
    journal ever holding an e-mail address or name (audit P-12)."""
    if not address:
        return "-"
    return hashlib.sha256(address.strip().lower().encode()).hexdigest()[:12]


class LogProvider:
    """Always-available provider that logs instead of sending. Keeps routing
    observable in dev/test without any external dependency. Logs only a hash
    prefix of the recipient, never the address or the body."""

    name = "log"
    configured = True

    async def send(self, message: ChannelMessage) -> None:
        logger.info(
            "notify[log] to=%s subject=%s", address_ref(message.to_email or message.to_name), message.subject
        )


class EmailSmtpProvider:
    name = "email"

    def __init__(self) -> None:
        self.host = settings.SMTP_HOST or ""
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER or ""
        self.password = settings.SMTP_PASSWORD or ""
        self.sender = settings.SMTP_FROM or self.user or "no-reply@vidhisangh.com"
        self.use_tls = settings.SMTP_TLS

    @property
    def configured(self) -> bool:
        return bool(self.host)

    async def send(self, message: ChannelMessage) -> None:
        if not message.to_email:
            raise ValueError("no recipient email address")
        email = EmailMessage()
        email["From"] = self.sender
        email["To"] = message.to_email
        email["Subject"] = message.subject
        body = message.body
        if message.link:
            body = f"{body}\n\n{message.link}"
        email.set_content(body)
        # Small, synchronous SMTP send — fine for the current inline path.
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(email)


class SlackWebhookProvider:
    name = "slack"

    def __init__(self) -> None:
        self.webhook = getattr(settings, "SLACK_WEBHOOK", None) or os.environ.get("VS_SLACK_WEBHOOK", "")

    @property
    def configured(self) -> bool:
        return bool(self.webhook)

    async def send(self, message: ChannelMessage) -> None:
        text = f"*{message.subject}*\n{message.body}"
        if message.link:
            text = f"{text}\n{message.link}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self.webhook, json={"text": text})
            resp.raise_for_status()


class ChannelRegistry:
    """Resolves a :class:`NotificationChannel` to its provider (or ``None``)."""

    def __init__(self, providers: dict[NotificationChannel, ChannelProvider]) -> None:
        self._providers = providers

    def provider_for(self, channel: NotificationChannel) -> ChannelProvider | None:
        return self._providers.get(channel)


_registry: ChannelRegistry | None = None


def _build_registry() -> ChannelRegistry:
    email = EmailSmtpProvider()
    slack = SlackWebhookProvider()
    return ChannelRegistry(
        {
            # in_app is handled directly by the notifications service, not here.
            NotificationChannel.EMAIL: email if email.configured else LogProvider(),
            NotificationChannel.SLACK: slack if slack.configured else LogProvider(),
            # sms / whatsapp / push / teams: no provider yet → recorded as skipped.
        }
    )


def get_channels() -> ChannelRegistry:
    """Process-wide channel registry, built once from the environment."""
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return _registry


def reset_channels() -> None:
    """Test hook: force the registry to rebuild (e.g. after changing env vars)."""
    global _registry
    _registry = None
