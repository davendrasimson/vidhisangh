"""Production-default contact verification and WhatsApp authentication contracts."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.channels import ChannelRegistry
from app.core.config import settings
from app.modules.identity.models import PhoneOtpChallenge, User
from app.modules.identity.registration_alerts import deliver_verification_next
from app.modules.notifications.models import NotificationChannel

API = "/api/v1/auth"


@pytest.fixture(autouse=True)
def require_verification(monkeypatch):
    monkeypatch.setattr(settings, "REGISTRATION_REQUIRE_VERIFICATION", True)


@pytest.fixture
def whatsapp(monkeypatch):
    sent = []

    async def send(phone, code):
        sent.append((phone, code))

    monkeypatch.setattr("app.modules.identity.phone_otp.send_whatsapp_code", send)
    return sent


@pytest.fixture
def email_provider(monkeypatch):
    class Mail:
        name = "email"
        configured = True
        fail = False

        def __init__(self):
            self.sent = []

        async def send(self, message):
            if self.fail:
                raise OSError("temporary outage")
            self.sent.append(message)

    mail = Mail()
    monkeypatch.setattr(
        "app.modules.identity.registration_alerts.get_channels",
        lambda: ChannelRegistry({NotificationChannel.EMAIL: mail}),
    )
    return mail


def registration(password, **extra):
    return dict(
        full_name="Mobile Advocate",
        practice_type="individual",
        password=password,
        accept_terms=True,
        **extra,
    )


async def code_for(client, whatsapp, phone="+919876543210", purpose="register"):
    response = await client.post(
        f"{API}/whatsapp/request", json={"phone": phone, "purpose": purpose}
    )
    assert response.status_code == 200, response.text
    return response.json()["challenge_id"], whatsapp[-1][1]


async def test_email_signup_requires_single_use_link(
    client, session_factory, strong_password, email_provider
):
    data = registration(strong_password, email="verify-new@example.com")
    result = await client.post(f"{API}/register", json=data)
    assert result.status_code == 201, result.text
    assert result.json()["verification_required"] is True
    assert "access_token" not in result.json()
    assert "set-cookie" not in result.headers
    login = {"email": data["email"], "password": strong_password}
    assert (await client.post(f"{API}/login", json=login)).status_code == 403
    async with session_factory() as session:
        assert await deliver_verification_next(session)
        await session.commit()
    assert len(email_provider.sent) == 1
    token = email_provider.sent[0].link.rsplit("/", 1)[-1]
    response = await client.post(f"{API}/verify-email/{token}")
    assert response.status_code == 200
    assert "set-cookie" not in response.headers  # click validates; it does not silently log in
    assert (await client.post(f"{API}/verify-email/{token}")).status_code == 404
    assert (await client.post(f"{API}/login", json=login)).status_code == 200


async def test_verification_delivery_retries_and_resend_invalidates_old_link(
    client,
    session_factory,
    strong_password,
    email_provider,
):
    await client.post(
        f"{API}/register", json=registration(strong_password, email="retry@example.com")
    )
    async with session_factory() as session:
        user = await session.scalar(select(User))
        old = user.email_verification_delivery_token
        email_provider.fail = True
        assert await deliver_verification_next(session)
        await session.commit()
        assert user.email_verification_attempts == 1
        assert user.email_verification_delivery_token == old
        assert not await deliver_verification_next(session)
    response = await client.post(
        f"{API}/resend-verification-public", json={"email": "retry@example.com"}
    )
    assert response.status_code == 202
    assert (await client.post(f"{API}/verify-email/{old}")).status_code == 404
    email_provider.fail = False
    async with session_factory() as session:
        assert await deliver_verification_next(session)
        await session.commit()
        assert not await deliver_verification_next(session)
    assert len(email_provider.sent) == 1


async def test_email_link_expiry(client, session_factory, strong_password):
    await client.post(
        f"{API}/register", json=registration(strong_password, email="expired@example.com")
    )
    async with session_factory() as session:
        user = await session.scalar(select(User))
        token = user.email_verification_delivery_token
        user.email_verification_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert (await client.post(f"{API}/verify-email/{token}")).status_code == 422
    assert (
        await client.post(
            f"{API}/login", json={"email": "expired@example.com", "password": strong_password}
        )
    ).status_code == 403


async def test_mobile_signup_and_passwordless_login(
    client, session_factory, strong_password, whatsapp
):
    challenge, code = await code_for(client, whatsapp, phone="9876543210")
    response = await client.post(
        f"{API}/register",
        json=registration(
            strong_password,
            phone="+91 9876543210",
            phone_challenge_id=challenge,
            phone_code=code,
            add_sample_data=True,
        ),
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    me = await client.get(f"{API}/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["email"] is None
    assert me.json()["phone"] == "+919876543210"
    assert me.json()["is_phone_verified"] is True
    for path in ["/api/v1/sample-data", "/api/v1/tenants/users", "/api/v1/rates/cards"]:
        # Both identity projection and sample workspace must accept no email.
        result = await client.get(path, headers=headers)
        assert result.status_code == 200, result.text
    challenge, code = await code_for(client, whatsapp, purpose="login")
    response = await client.post(
        f"{API}/whatsapp/login", json={"challenge_id": challenge, "code": code}
    )
    assert response.status_code == 200, response.text
    assert (
        await client.post(f"{API}/whatsapp/login", json={"challenge_id": challenge, "code": code})
    ).status_code == 401
    async with session_factory() as session:
        rows = (await session.scalars(select(PhoneOtpChallenge))).all()
        assert all(row.code_hash != code and len(row.code_hash) == 64 for row in rows)


async def test_both_contacts_still_require_email_link(client, strong_password, whatsapp):
    challenge, code = await code_for(client, whatsapp)
    response = await client.post(
        f"{API}/register",
        json=registration(
            strong_password,
            email="both@example.com",
            phone="+919876543210",
            phone_challenge_id=challenge,
            phone_code=code,
        ),
    )
    assert response.status_code == 201
    assert response.json()["verification_required"] is True
    challenge, code = await code_for(client, whatsapp, purpose="login")
    assert (
        await client.post(f"{API}/whatsapp/login", json={"challenge_id": challenge, "code": code})
    ).status_code == 403


async def test_contact_required_and_phone_cannot_be_claimed_without_code(client, strong_password):
    for extra in ({}, {"email": "", "phone": ""}, {"phone": "+919876543210"}):
        response = await client.post(f"{API}/register", json=registration(strong_password, **extra))
        assert response.status_code == 422


async def test_wrong_codes_are_bounded_and_persisted(
    client, session_factory, strong_password, whatsapp
):
    challenge, code = await code_for(client, whatsapp)
    wrong = "000000" if code != "000000" else "111111"
    data = registration(
        strong_password, phone="+919876543210", phone_challenge_id=challenge, phone_code=wrong
    )
    for _ in range(5):
        assert (await client.post(f"{API}/register", json=data)).status_code == 401
    data["phone_code"] = code
    assert (await client.post(f"{API}/register", json=data)).status_code == 401
    async with session_factory() as session:
        row = await session.scalar(select(PhoneOtpChallenge))
        assert row.attempts == 5 and row.consumed
        assert await session.scalar(select(User)) is None


async def test_phone_code_binding_resend_and_expiry(
    client, session_factory, strong_password, whatsapp
):
    first, old_code = await code_for(client, whatsapp)
    second, code = await code_for(client, whatsapp)
    data = registration(
        strong_password, phone="+919876543210", phone_challenge_id=first, phone_code=old_code
    )
    assert (await client.post(f"{API}/register", json=data)).status_code == 401
    data.update(phone="+919876543211", phone_challenge_id=second, phone_code=code)
    assert (await client.post(f"{API}/register", json=data)).status_code == 401
    data["phone"] = "+919876543210"
    async with session_factory() as session:
        rows = (await session.scalars(select(PhoneOtpChallenge))).all()
        for row in rows:
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert (await client.post(f"{API}/register", json=data)).status_code == 401


async def test_unknown_mobile_login_does_not_send_or_issue_tokens(client, whatsapp):
    response = await client.post(
        f"{API}/whatsapp/request", json={"phone": "+919876543210", "purpose": "login"}
    )
    assert response.status_code == 200
    assert whatsapp == []
    assert (
        await client.post(
            f"{API}/whatsapp/login",
            json={"challenge_id": response.json()["challenge_id"], "code": "123456"},
        )
    ).status_code == 401


async def test_whatsapp_outage_creates_no_challenge(client, session_factory, monkeypatch):
    from app.core.exceptions import ServiceUnavailableError

    async def unavailable(phone, code):
        raise ServiceUnavailableError("unavailable")

    monkeypatch.setattr("app.modules.identity.phone_otp.send_whatsapp_code", unavailable)
    response = await client.post(
        f"{API}/whatsapp/request", json={"phone": "+919876543210", "purpose": "register"}
    )
    assert response.status_code == 503
    async with session_factory() as session:
        assert await session.scalar(select(PhoneOtpChallenge)) is None


async def test_whatsapp_login_preserves_mfa(client, session_factory, strong_password, whatsapp):
    import pyotp

    challenge, code = await code_for(client, whatsapp)
    registered = await client.post(
        f"{API}/register",
        json=registration(
            strong_password,
            phone="+919876543210",
            phone_challenge_id=challenge,
            phone_code=code,
        ),
    )
    assert registered.status_code == 201
    secret = pyotp.random_base32()
    async with session_factory() as session:
        user = await session.scalar(select(User))
        user.mfa_enabled = True
        user.mfa_secret = secret
        await session.commit()
    challenge, code = await code_for(client, whatsapp, purpose="login")
    body = {"challenge_id": challenge, "code": code}
    response = await client.post(f"{API}/whatsapp/login", json=body)
    assert response.status_code == 401
    assert response.json()["title"] == "mfa_required"
    body["mfa_code"] = pyotp.TOTP(secret).now()
    assert (await client.post(f"{API}/whatsapp/login", json=body)).status_code == 200


async def test_whatsapp_disabled_user_cannot_use_previously_sent_code(
    client,
    session_factory,
    strong_password,
    whatsapp,
):
    challenge, code = await code_for(client, whatsapp)
    await client.post(
        f"{API}/register",
        json=registration(
            strong_password,
            phone="+919876543210",
            phone_challenge_id=challenge,
            phone_code=code,
        ),
    )
    challenge, code = await code_for(client, whatsapp, purpose="login")
    async with session_factory() as session:
        user = await session.scalar(select(User))
        user.is_active = False
        await session.commit()
    assert (
        await client.post(f"{API}/whatsapp/login", json={"challenge_id": challenge, "code": code})
    ).status_code == 401


async def test_whatsapp_phone_throttle_is_normalized_and_fails_closed(
    client, whatsapp, monkeypatch
):
    monkeypatch.setattr(settings, "RATE_LIMITING_ENABLED", True)
    first = await client.post(
        f"{API}/whatsapp/request", json={"phone": "9876543210", "purpose": "register"}
    )
    assert first.status_code == 200
    second = await client.post(
        f"{API}/whatsapp/request", json={"phone": "+91 9876543210", "purpose": "register"}
    )
    assert second.status_code == 429
    assert len(whatsapp) == 1

    def unavailable():
        raise OSError("cache unavailable")

    monkeypatch.setattr("app.core.ratelimit.get_redis", unavailable)
    third = await client.post(
        f"{API}/whatsapp/request", json={"phone": "+919876543211", "purpose": "register"}
    )
    assert third.status_code == 503
    assert len(whatsapp) == 1
