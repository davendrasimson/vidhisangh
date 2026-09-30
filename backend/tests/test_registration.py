"""Minimal signup contracts and durable, credential-free owner alerts."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.channels import ChannelRegistry
from app.modules.identity.models import RegistrationAlert, User
from app.modules.identity.registration_alerts import deliver_next
from app.modules.notifications.models import NotificationChannel
from app.modules.tenancy.models import Tenant


def payload(password, **extra):
    return dict(
        full_name="  Solo Advocate  ",
        email="signup@example.com",
        password=password,
        accept_terms=True,
        practice_type="individual",
        **extra,
    )


@pytest.mark.parametrize(
    "practice,organisation,expected_type",
    [
        ("individual", None, "individual"),
        ("firm", " Example Chambers ", "small_firm"),
    ],
)
async def test_signup_practice_and_alert(
    client, session_factory, strong_password, practice, organisation, expected_type
):
    data = payload(strong_password)
    data["practice_type"] = practice
    if organisation is not None:
        data["organisation_name"] = organisation
    response = await client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 201, response.text
    async with session_factory() as session:
        tenant = await session.scalar(select(Tenant))
        assert tenant.type == expected_type
        assert tenant.name == (organisation.strip() if organisation else "Solo Advocate")
        alert = await session.scalar(select(RegistrationAlert))
        assert alert.recipient == "ds@simsononline.com"
        assert alert.sent_at is None and alert.attempts == 0
    duplicate = await client.post("/api/v1/auth/register", json=data)
    assert duplicate.status_code == 409
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(RegistrationAlert)) == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"practice_type": "firm"},
        {"practice_type": "firm", "organisation_name": "  "},
        {"practice_type": "enterprise"},
        {"full_name": "  "},
    ],
)
async def test_invalid_registration_has_no_alert(client, session_factory, strong_password, extra):
    data = payload(strong_password)
    data.update(extra)
    response = await client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 422
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(RegistrationAlert)) == 0


async def test_alert_retries_and_sends_once_without_credentials(
    client, session_factory, strong_password, monkeypatch
):
    response = await client.post("/api/v1/auth/register", json=payload(strong_password))
    assert response.status_code == 201
    messages = []

    class Mail:
        name = "email"
        configured = True
        fail = True

        async def send(self, message):
            if self.fail:
                raise OSError("temporary SMTP outage")
            messages.append(message)

    mail = Mail()
    monkeypatch.setattr(
        "app.modules.identity.registration_alerts.get_channels",
        lambda: ChannelRegistry({NotificationChannel.EMAIL: mail}),
    )
    async with session_factory() as session:
        assert await deliver_next(session)
        await session.commit()
        alert = await session.scalar(select(RegistrationAlert))
        assert alert.attempts == 1 and alert.sent_at is None
        assert not await deliver_next(session)  # backoff
        alert.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    mail.fail = False
    async with session_factory() as session:
        assert await deliver_next(session)
        await session.commit()
        assert not await deliver_next(session)
    assert len(messages) == 1
    message = messages[0]
    assert message.to_email == "ds@simsononline.com"
    for detail in ["Solo Advocate", "signup@example.com", "Individual practice", "User ID:", "IST"]:
        assert detail in message.body
    for secret in [
        strong_password,
        response.json()["access_token"],
        response.json()["refresh_token"],
    ]:
        if secret:
            assert secret not in message.body


async def test_rolled_back_signup_leaves_no_alert(session_factory, strong_password):
    from app.modules.identity.schemas import RegisterRequest
    from app.modules.identity.service import AuthService

    async with session_factory() as session:
        await AuthService(session).register(RegisterRequest(**payload(strong_password)))
        await session.flush()
        await session.rollback()
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(RegistrationAlert)) == 0
        assert await session.scalar(select(func.count()).select_from(User)) == 0


async def test_legacy_signup_without_practice_type(client, session_factory, strong_password):
    data = payload(strong_password, organisation_name="Existing Client Chambers")
    del data["practice_type"]
    response = await client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 201, response.text
    async with session_factory() as session:
        tenant = await session.scalar(select(Tenant))
        assert tenant.name == "Existing Client Chambers"
        assert tenant.type == "individual"


@pytest.mark.parametrize("missing_model", [User, Tenant])
async def test_orphaned_alert_does_not_block_queue(
    client, session_factory, strong_password, monkeypatch, missing_model
):
    response = await client.post("/api/v1/auth/register", json=payload(strong_password))
    assert response.status_code == 201
    async with session_factory() as session:
        original_get = session.get

        async def get(model, key, **kwargs):
            if model is missing_model:
                return None
            return await original_get(model, key, **kwargs)

        monkeypatch.setattr(session, "get", get)
        assert await deliver_next(session)
        await session.commit()
        assert not await deliver_next(session)
        assert await session.scalar(select(func.count()).select_from(RegistrationAlert)) == 0
