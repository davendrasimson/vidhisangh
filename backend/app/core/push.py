"""Sending seam for mobile push notifications (Firebase Cloud Messaging, HTTP v1).

``get_push_sender()`` is ``None`` until ``VS_FCM_CREDENTIALS_FILE`` points at a
Firebase service-account key (a systemd credential in production); nothing is
sent then. Tests install a recorder with ``set_push_sender``. The access token
is a self-signed JWT exchanged at Google's token endpoint and reused for 50
minutes. Never log tokens, device tokens or message text.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import httpx
import jwt

from app.core.config import settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

Result = Literal["sent", "unregistered", "failed"]


@dataclass
class PushMessage:
    title: str
    body: str
    link: str | None = None


class PushSender(Protocol):
    async def send(self, device_token: str, message: PushMessage) -> Result: ...


class FcmSender:
    def __init__(self, credentials_file: str) -> None:
        self._file = credentials_file
        self._token: str | None = None
        self._expires = 0.0
        self._key: dict | None = None

    def _credentials(self) -> dict:
        if self._key is None:
            self._key = json.loads(Path(self._file).read_text())
        return self._key

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._expires:
            return self._token
        key = self._credentials()
        now = int(time.time())
        assertion = jwt.encode(
            {"iss": key["client_email"], "scope": SCOPE, "aud": TOKEN_URL, "iat": now, "exp": now + 3600},
            key["private_key"], algorithm="RS256",
        )
        response = await client.post(TOKEN_URL, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
        response.raise_for_status()
        self._token, self._expires = response.json()["access_token"], time.time() + 50 * 60
        return self._token

    async def send(self, device_token: str, message: PushMessage) -> Result:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                access = await self._access_token(client)
                project = self._credentials()["project_id"]
                body = {"message": {
                    "token": device_token,
                    "notification": {"title": message.title[:100], "body": message.body[:500]},
                    "data": {"link": message.link or "/app/notifications"},
                    "android": {"priority": "high", "notification": {"channel_id": "default", "icon": "ic_stat_notify", "color": "#215DCC"}},
                }}
                response = await client.post(
                    f"https://fcm.googleapis.com/v1/projects/{project}/messages:send",
                    headers={"Authorization": f"Bearer {access}"}, json=body,
                )
            if response.status_code == 200:
                return "sent"
            if response.status_code in (400, 404):
                code = json.dumps(response.json().get("error", {}).get("details", ""))
                if "UNREGISTERED" in code or response.status_code == 404 or "registration token" in response.text:
                    return "unregistered"
            return "failed"
        except (httpx.HTTPError, ValueError, KeyError, OSError, jwt.PyJWTError):
            return "failed"


_override: PushSender | None = None
_override_set = False
_cached: FcmSender | None = None


def get_push_sender() -> PushSender | None:
    global _cached
    if _override_set:
        return _override
    if not settings.FCM_CREDENTIALS_FILE:
        return None
    if _cached is None or _cached._file != settings.FCM_CREDENTIALS_FILE:
        _cached = FcmSender(settings.FCM_CREDENTIALS_FILE)
    return _cached


def set_push_sender(sender: PushSender | None, *, active: bool = True) -> None:
    """Test hook. ``active=False`` restores the configured sender."""
    global _override, _override_set
    _override, _override_set = sender, active
