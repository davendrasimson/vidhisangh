"""Sending seam for invitation emails (separate from app/core/channels.py).

``get_outreach_sender()`` is ``None`` until ``VS_OUTREACH_SMTP_HOST`` is set:
then nothing is sent and contacts stay queued. Tests install a recorder with
``set_outreach_sender``. Every message carries ``List-Unsubscribe`` and
``List-Unsubscribe-Post: List-Unsubscribe=One-Click`` (RFC 8058), so Gmail and
Outlook show their own Unsubscribe button and it works without opening a page.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

from app.core.config import settings

SMTP_TIMEOUT_SECONDS = 30


@dataclass
class OutreachMessage:
    to: str
    subject: str
    text: str
    html: str
    one_click_url: str
    unsubscribe_page: str


class RecipientRefused(Exception):
    """The receiving server refused the address: a hard bounce."""


class OutreachSender(Protocol):
    async def send(self, message: OutreachMessage) -> None: ...


class SmtpOutreachSender:
    def __init__(self) -> None:
        self.host = settings.OUTREACH_SMTP_HOST or ""
        self.port = settings.OUTREACH_SMTP_PORT
        self.user = settings.OUTREACH_SMTP_USER or ""
        self.sender = settings.OUTREACH_FROM

    async def send(self, message: OutreachMessage) -> None:
        await asyncio.to_thread(self._send, message)

    def _send(self, message: OutreachMessage) -> None:
        email = EmailMessage()
        email["From"] = self.sender
        email["To"] = message.to
        email["Reply-To"] = settings.OUTREACH_REPLY_TO
        email["Subject"] = message.subject
        email["Date"] = formatdate(localtime=False, usegmt=True)
        domain = self.sender.rsplit("@", 1)[-1].rstrip(">")
        email["Message-ID"] = make_msgid(domain=domain)
        email["List-Unsubscribe"] = f"<{message.one_click_url}>, <{message.unsubscribe_page}>"
        email["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        # Brevo groups transactional statistics and webhook events by this tag.
        email["X-Mailin-Tag"] = "invitation"
        email.set_content(message.text)
        email.add_alternative(message.html, subtype="html")
        connection = (
            smtplib.SMTP_SSL(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS, context=ssl.create_default_context())
            if self.port == 465
            else smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS)
        )
        try:
            if self.port != 465:
                connection.starttls(context=ssl.create_default_context())
            if self.user:
                connection.login(self.user, settings.outreach_smtp_password)
            try:
                connection.send_message(email)
            except smtplib.SMTPRecipientsRefused as exc:
                raise RecipientRefused(str(exc)) from exc
            try:
                connection.quit()
            except smtplib.SMTPServerDisconnected:
                pass
        finally:
            connection.close()


_override: OutreachSender | None = None
_override_set = False


def get_outreach_sender() -> OutreachSender | None:
    if _override_set:
        return _override
    return SmtpOutreachSender() if settings.OUTREACH_SMTP_HOST else None


def set_outreach_sender(sender: OutreachSender | None, *, active: bool = True) -> None:
    """Test hook. ``active=False`` restores the configured sender."""
    global _override, _override_set
    _override, _override_set = sender, active
