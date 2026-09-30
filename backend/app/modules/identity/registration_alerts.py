"""Durable operational signup emails; no passwords or authentication tokens.

Rows are committed with registration. Workers lock one row at a time so multiple
API processes cannot send it concurrently. SMTP failures retry with backoff;
a process failure after SMTP accepts mail but before commit can cause a duplicate.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channels import ChannelMessage, get_channels
from app.core.config import settings
from app.core.database import session_scope
from app.modules.identity.models import PhoneOtpChallenge, RegistrationAlert, User
from app.modules.notifications.models import NotificationChannel
from app.modules.tenancy.models import Tenant

log = structlog.get_logger(__name__)


def queue_registration_alert(session: AsyncSession, user: User, sample_data: bool) -> None:
    if settings.REGISTRATION_ALERT_EMAIL:
        session.add(
            RegistrationAlert(
                user_id=user.id,
                recipient=settings.REGISTRATION_ALERT_EMAIL,
                sample_data=sample_data,
                next_attempt_at=datetime.now(UTC),
            )
        )


async def deliver_next(session: AsyncSession) -> bool:
    now = datetime.now(UTC)
    alert = await session.scalar(
        select(RegistrationAlert)
        .where(RegistrationAlert.sent_at.is_(None), RegistrationAlert.next_attempt_at <= now)
        .order_by(RegistrationAlert.next_attempt_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if alert is None:
        return False
    user = await session.get(User, alert.user_id)
    tenant = await session.get(Tenant, user.tenant_id) if user is not None else None
    if user is None or tenant is None:
        # A stale row must not stop later registrations from being delivered.
        log.warning("registration_alert_orphaned", alert_id=str(alert.id))
        await session.delete(alert)
        await session.flush()
        return True
    registered = (
        alert.created_at.replace(tzinfo=UTC)
        if alert.created_at.tzinfo is None
        else alert.created_at
    )
    practice = "Individual practice" if tenant.type == "individual" else "Firm / chamber"
    registered_text = registered.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d/%m/%Y, %I:%M %p")
    message = ChannelMessage(
        to_email=alert.recipient,
        to_name=None,
        subject="New VidhiSangh registration",
        body=(
            "A new account has registered on VidhiSangh.\n\n"
            f"Name: {user.full_name}\nEmail: {user.email or 'Not provided'}\n"
            f"Mobile: {user.phone or 'Not provided'}\n"
            f"Practice type: {practice}\nWorkspace: {tenant.name}\n"
            f"Registered: {registered_text} IST\n"
            f"Plan: {tenant.plan}\n"
            f"Guided sample workspace: {'Yes' if alert.sample_data else 'No'}\n"
            f"User ID: {user.id}\nWorkspace ID: {tenant.id}\n"
            f"Email verification: {'pending' if user.email else 'not applicable'}\n"
            f"Mobile verified: {'Yes' if user.is_phone_verified else 'No'}\n"
        ),
        link="https://admin.vidhisangh.com/platform-admin",
    )
    alert.attempts += 1
    try:
        provider = get_channels().provider_for(NotificationChannel.EMAIL)
        if provider is None or not provider.configured or provider.name == "log":
            raise RuntimeError("SMTP is not configured")
        await provider.send(message)
    except Exception as exc:  # keep the row for a later retry
        alert.next_attempt_at = now + timedelta(
            seconds=min(60 * 2 ** min(alert.attempts - 1, 6), 3600)
        )
        log.warning(
            "registration_alert_retry", alert_id=str(alert.id), error_type=type(exc).__name__
        )
    else:
        alert.sent_at = datetime.now(UTC)
        log.info("registration_alert_sent", alert_id=str(alert.id))
    await session.flush()
    return True


async def deliver_verification_next(session: AsyncSession) -> bool:
    now = datetime.now(UTC)
    user = await session.scalar(
        select(User)
        .where(
            User.email_verification_delivery_token.is_not(None),
            User.email_verification_next_attempt_at <= now,
        )
        .order_by(User.email_verification_next_attempt_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if user is None:
        return False
    expires = user.email_verification_expires_at
    expired = (
        expires is None
        or (expires.replace(tzinfo=UTC) if expires.tzinfo is None else expires) <= now
    )
    if not user.email or user.deleted_at or user.is_email_verified or not user.is_active or expired:
        user.email_verification_delivery_token = None
        user.email_verification_next_attempt_at = None
        await session.flush()
        return True
    user.email_verification_attempts += 1
    try:
        provider = get_channels().provider_for(NotificationChannel.EMAIL)
        if provider is None or not provider.configured or provider.name == "log":
            raise RuntimeError("SMTP is not configured")
        await provider.send(
            ChannelMessage(
                to_email=user.email,
                to_name=user.full_name,
                subject="Verify your VidhiSangh email address",
                body=(
                    f"Hello {user.full_name},\n\nOpen the link below to verify your email "
                    "and activate your VidhiSangh account. You can sign in after verification.\n"
                    f"This link expires in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours. "
                    "If you did not register, ignore this email."
                ),
                link=f"{settings.PUBLIC_APP_URL.rstrip('/')}/auth/verify-email/"
                f"{user.email_verification_delivery_token}",
            )
        )
    except Exception as exc:
        user.email_verification_next_attempt_at = now + timedelta(
            seconds=min(60 * 2 ** min(user.email_verification_attempts - 1, 6), 3600)
        )
        log.warning("verification_email_retry", user_id=str(user.id), error_type=type(exc).__name__)
    else:
        user.email_verification_delivery_token = None
        user.email_verification_next_attempt_at = None
        log.info("verification_email_sent", user_id=str(user.id))
    await session.flush()
    return True


async def run_delivery_loop() -> None:
    while True:
        try:
            async with session_scope(bypass_rls=True) as session:
                await session.execute(
                    delete(PhoneOtpChallenge).where(
                        PhoneOtpChallenge.expires_at < datetime.now(UTC) - timedelta(days=1)
                    )
                )
            # Bound each batch; each delivery gets its own short transaction.
            for _ in range(20):
                async with session_scope(bypass_rls=True) as session:
                    verified = await deliver_verification_next(session)
                async with session_scope(bypass_rls=True) as session:
                    alerted = await deliver_next(session)
                if not verified and not alerted:
                    break
        except Exception as exc:  # recover from temporary database outages
            log.warning("registration_alert_worker_retry", error_type=type(exc).__name__)
        await asyncio.sleep(5)
