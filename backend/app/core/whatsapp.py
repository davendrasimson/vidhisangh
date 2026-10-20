"""Sending seam for WhatsApp template messages (other than sign-in codes).

``get_whatsapp_sender()`` is ``None`` until the WhatsApp Cloud API is configured
(``VS_WA_PHONE_NUMBER_ID`` plus a token); callers then skip sending. Tests
install a recorder with ``set_whatsapp_sender``. Never log tokens, numbers or
message bodies.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import settings


class WhatsAppError(Exception):
    """The provider refused or could not be reached. Carries no message content."""


class WhatsAppSender(Protocol):
    async def send_template(self, phone: str, template: str, lang: str, body: list[str]) -> str: ...


def _token() -> str:
    if settings.WA_ACCESS_TOKEN:
        return settings.WA_ACCESS_TOKEN
    if settings.WA_ACCESS_TOKEN_FILE:
        try:
            return Path(settings.WA_ACCESS_TOKEN_FILE).read_text().strip()
        except OSError:
            return ""
    return ""


class CloudApiSender:
    async def send_template(self, phone: str, template: str, lang: str, body: list[str]) -> str:
        """Returns the provider's message id."""
        token = await asyncio.to_thread(_token)
        if not token:
            raise WhatsAppError("no token")
        payload = {
            "messaging_product": "whatsapp",
            "to": phone.lstrip("+"),
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": lang},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": v} for v in body]}],
            },
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"https://graph.facebook.com/{settings.WA_API_VERSION}/{settings.WA_PHONE_NUMBER_ID}/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
            if response.status_code >= 400:
                error = (response.json() or {}).get("error", {}) if response.content else {}
                raise WhatsAppError(f"HTTP {response.status_code} code {error.get('code', '?')}")
            messages = response.json().get("messages") or []
            if not messages:
                raise WhatsAppError("no message accepted")
            return str(messages[0].get("id", ""))
        except (httpx.HTTPError, ValueError) as exc:
            raise WhatsAppError(type(exc).__name__) from exc


_override: WhatsAppSender | None = None
_override_set = False


def get_whatsapp_sender() -> WhatsAppSender | None:
    if _override_set:
        return _override
    if settings.WA_PHONE_NUMBER_ID and (settings.WA_ACCESS_TOKEN or settings.WA_ACCESS_TOKEN_FILE):
        return CloudApiSender()
    return None


def set_whatsapp_sender(sender: WhatsAppSender | None, *, active: bool = True) -> None:
    """Test hook. ``active=False`` restores the configured sender."""
    global _override, _override_set
    _override, _override_set = sender, active
