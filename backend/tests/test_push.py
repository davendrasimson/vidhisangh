"""Push notifications: phones registered by the app receive each notification."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.push import PushMessage, set_push_sender
from app.modules.notifications.models import NotificationType, PushDevice
from app.modules.notifications.service import create_notification

pytestmark = pytest.mark.asyncio
API = "/api/v1"
TOKEN = "fcm-token-" + "x" * 40


class Recorder:
    def __init__(self, result="sent") -> None:
        self.sent: list[tuple[str, PushMessage]] = []
        self.result = result

    async def send(self, device_token, message):
        self.sent.append((device_token, message))
        return self.result


@pytest.fixture
def push():
    recorder = Recorder()
    set_push_sender(recorder)
    yield recorder
    set_push_sender(None, active=False)


async def _member(client: AsyncClient, pw: str, email: str) -> tuple[dict, str]:
    r = await client.post(f"{API}/auth/register", json={"organisation_name": email, "full_name": "Adv. Rao",
                                                         "email": email, "password": pw, "accept_terms": True})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return h, (await client.get(f"{API}/auth/me", headers=h)).json()["id"]


async def test_registered_phone_gets_each_notification_until_signed_out(
    client: AsyncClient, strong_password: str, session_factory, push,
) -> None:
    import uuid

    h, uid = await _member(client, strong_password, "rao@example.com")
    assert (await client.post(f"{API}/notifications/devices", headers=h, json={"token": TOKEN, "platform": "android"})).status_code == 204
    assert (await client.post(f"{API}/notifications/devices", headers=h, json={"token": TOKEN, "platform": "android"})).status_code == 204
    async with session_factory() as s:
        await create_notification(s, user_id=uuid.UUID(uid), type=NotificationType.CONNECTION_REQUEST,
                                  message="Adv. Mehta wants to connect", link="/app/people")
        await s.commit()
        assert len((await s.scalars(select(PushDevice))).all()) == 1
    assert push.sent == [(TOKEN, PushMessage(title="VidhiSangh", body="Adv. Mehta wants to connect", link="/app/people"))]

    # Switched off: nothing more.
    await client.put(f"{API}/notifications/preferences/push", headers=h, json={"enabled": False, "types": []})
    async with session_factory() as s:
        await create_notification(s, user_id=uuid.UUID(uid), type=NotificationType.MENTION, message="m")
        await s.commit()
    assert len(push.sent) == 1
    await client.put(f"{API}/notifications/preferences/push", headers=h, json={"enabled": True, "types": []})

    # Another member signs in on the same phone: the token moves; sign-out removes it.
    h2, uid2 = await _member(client, strong_password, "mehta@example.com")
    await client.post(f"{API}/notifications/devices", headers=h2, json={"token": TOKEN, "platform": "android"})
    async with session_factory() as s:
        assert str((await s.scalar(select(PushDevice))).user_id) == uid2
    assert (await client.post(f"{API}/notifications/devices/remove", headers=h2, json={"token": TOKEN, "platform": "android"})).status_code == 204
    async with session_factory() as s:
        assert (await s.scalar(select(PushDevice))) is None


async def test_a_token_firebase_no_longer_knows_is_dropped(client: AsyncClient, strong_password: str, session_factory) -> None:
    import uuid

    gone = Recorder("unregistered")
    set_push_sender(gone)
    try:
        h, uid = await _member(client, strong_password, "rao@example.com")
        await client.post(f"{API}/notifications/devices", headers=h, json={"token": TOKEN, "platform": "android"})
        async with session_factory() as s:
            await create_notification(s, user_id=uuid.UUID(uid), type=NotificationType.MENTION, message="m")
            await s.commit()
            assert (await s.scalar(select(PushDevice))) is None
    finally:
        set_push_sender(None, active=False)


async def test_firebase_sender_signs_in_and_sends(tmp_path, monkeypatch) -> None:
    import json

    import httpx
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app.core.push import FcmSender

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    creds = tmp_path / "fcm.json"
    creds.write_text(json.dumps({"type": "service_account", "project_id": "vidhisangh-2c038",
                                 "client_email": "push@vidhisangh-2c038.iam.gserviceaccount.com", "private_key": pem}))
    calls = []

    async def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            assertion = dict(x.split("=", 1) for x in request.content.decode().split("&"))["assertion"]
            claims = jwt.decode(assertion, key.public_key(), algorithms=["RS256"], audience="https://oauth2.googleapis.com/token")
            assert claims["iss"].startswith("push@") and "firebase.messaging" in claims["scope"]
            return httpx.Response(200, json={"access_token": "ya29.test", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer ya29.test"
        body = json.loads(request.content)["message"]
        if body["token"] == "gone":
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}})
        assert body["notification"] == {"title": "VidhiSangh", "body": "Hello"} and body["data"] == {"link": "/app/people"}
        return httpx.Response(200, json={"name": "projects/x/messages/1"})

    original = httpx.AsyncClient
    monkeypatch.setattr("app.core.push.httpx.AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    sender = FcmSender(str(creds))
    assert await sender.send("device-1", PushMessage("VidhiSangh", "Hello", "/app/people")) == "sent"
    assert await sender.send("gone", PushMessage("VidhiSangh", "Hello", "/app/people")) == "unregistered"
    assert [c.url.host for c in calls].count("oauth2.googleapis.com") == 1  # token reused
    assert str(calls[1].url) == "https://fcm.googleapis.com/v1/projects/vidhisangh-2c038/messages:send"
