"""Tenant service — organisation lifecycle operations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from urllib.parse import urlparse

from app.core.exceptions import NotFoundError
from app.core.link_preview import assert_public_http_url
from app.modules.tenancy.models import Tenant, TenantStatus
from app.modules.tenancy.repository import TenantRepository
from app.modules.tenancy.schemas import (
    TenantDeleteResult,
    TenantNotificationSettings,
    TenantNotificationSettingsRead,
    TenantPrivacySettings,
    TenantPrivacySettingsRead,
    TenantUpdate,
)

NOTIFICATIONS_KEY = "notifications"
SLACK_WEBHOOK_KEY = "slack_webhook"
PRIVACY_KEY = "privacy"  # privacy agent: tenants.settings["privacy"]


def tenant_slack_webhook(tenant: Tenant | None) -> str | None:
    """The tenant's own Slack incoming-webhook URL, if configured."""
    if tenant is None:
        return None
    block = (tenant.settings or {}).get(NOTIFICATIONS_KEY) or {}
    url = block.get(SLACK_WEBHOOK_KEY)
    return url or None


class TenantService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = TenantRepository(session)

    async def get(self, tenant_id: uuid.UUID) -> Tenant:
        tenant = await self.repo.get_by_id(tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found.")
        return tenant

    async def update(self, tenant_id: uuid.UUID, data: TenantUpdate) -> Tenant:
        tenant = await self.get(tenant_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "settings" and value is not None:
                # The notifications block is managed by its own endpoint (it is
                # validated there); a generic settings write must not smuggle a URL in.
                # Managed blocks have their own endpoints; a generic settings
                # write must not clobber them.
                value = {k: v for k, v in value.items() if k not in (NOTIFICATIONS_KEY, PRIVACY_KEY)}
                value[NOTIFICATIONS_KEY] = (tenant.settings or {}).get(NOTIFICATIONS_KEY, {})
                value[PRIVACY_KEY] = (tenant.settings or {}).get(PRIVACY_KEY, {})
            setattr(tenant, field, value)
        return tenant

    @staticmethod
    def _settings_read(tenant: Tenant) -> TenantNotificationSettingsRead:
        url = tenant_slack_webhook(tenant)
        return TenantNotificationSettingsRead(
            slack_webhook_configured=url is not None,
            slack_webhook_host=urlparse(url).hostname if url else None,
        )

    async def notification_settings(self, tenant_id: uuid.UUID) -> TenantNotificationSettingsRead:
        return self._settings_read(await self.get(tenant_id))

    async def set_notification_settings(
        self, tenant_id: uuid.UUID, data: TenantNotificationSettings
    ) -> TenantNotificationSettingsRead:
        tenant = await self.get(tenant_id)
        settings = dict(tenant.settings or {})
        block = dict(settings.get(NOTIFICATIONS_KEY) or {})
        if data.slack_webhook:
            await assert_public_http_url(data.slack_webhook, require_https=True)
            block[SLACK_WEBHOOK_KEY] = data.slack_webhook
        else:
            block.pop(SLACK_WEBHOOK_KEY, None)
        settings[NOTIFICATIONS_KEY] = block
        tenant.settings = settings  # reassign: JSON columns need a new object to be detected
        return self._settings_read(tenant)

    # ── Privacy & offboarding (privacy agent) ────────────────────────
    async def privacy_settings(self, tenant_id: uuid.UUID) -> TenantPrivacySettingsRead:
        return self._privacy_read(await self.get(tenant_id))

    async def set_privacy_settings(
        self, tenant_id: uuid.UUID, data: TenantPrivacySettings
    ) -> TenantPrivacySettingsRead:
        tenant = await self.get(tenant_id)
        settings = dict(tenant.settings or {})
        block = dict(settings.get(PRIVACY_KEY) or {})
        block.update({k: v for k, v in data.model_dump(exclude_unset=True).items()})
        settings[PRIVACY_KEY] = block
        tenant.settings = settings
        return self._privacy_read(tenant)

    @staticmethod
    def _privacy_read(tenant: Tenant) -> TenantPrivacySettingsRead:
        from app.modules.privacy.config import privacy_setting
        from app.modules.privacy.service import SUB_PROCESSORS

        block = dict((tenant.settings or {}).get(PRIVACY_KEY) or {})
        block.setdefault("matter_retention_years", int(privacy_setting("LEGAL_HOLD_YEARS")))
        block.setdefault("directory_listing_default", False)
        return TenantPrivacySettingsRead(
            **{k: v for k, v in block.items() if k in TenantPrivacySettings.model_fields},
            dpa_version=str(privacy_setting("CURRENT_TERMS_VERSION")),
            sub_processors=[p["name"] for p in SUB_PROCESSORS],
        )

    async def cancel(
        self, tenant_id: uuid.UUID, *, actor_id: uuid.UUID, actor_label: str | None,
        confirm_slug: str, password: str,
    ) -> TenantDeleteResult:
        """Owner-initiated offboarding: the tenant is CANCELLED now, every user
        is disabled and signed out, and the retention job erases everything
        after the grace period (``erase_after``)."""
        from app.core import security
        from app.core.exceptions import AuthenticationError, ValidationError
        from app.modules.audit.service import record_audit
        from app.modules.identity.models import RefreshToken, User
        from app.modules.privacy.config import privacy_setting

        tenant = await self.get(tenant_id)
        if confirm_slug.strip().lower() != tenant.slug:
            raise ValidationError("Type the organisation's slug exactly to confirm deletion.")
        session = self.repo.session
        actor = await session.scalar(select(User).where(User.id == actor_id, User.tenant_id == tenant_id))
        if actor is None or not actor.hashed_password or not security.verify_password(password, actor.hashed_password):
            raise AuthenticationError("Password is incorrect.")
        now = datetime.now(UTC)
        tenant.status = TenantStatus.CANCELLED
        tenant.cancelled_at = now
        tenant.erase_after = now + timedelta(days=int(privacy_setting("TENANT_ERASE_GRACE_DAYS")))
        users = list((await session.execute(select(User).where(User.tenant_id == tenant_id, User.deleted_at.is_(None)))).scalars().all())
        for u in users:
            u.is_active = False
        tokens = (await session.execute(select(RefreshToken).where(RefreshToken.tenant_id == tenant_id, RefreshToken.revoked_at.is_(None)))).scalars().all()
        for t in tokens:
            t.revoked_at = now
            t.ip_address = None
            t.user_agent = None
        record_audit(
            session, tenant_id=tenant_id, actor_id=actor_id, actor_label=actor_label,
            action="tenant.cancelled", entity_type="tenant", entity_id=str(tenant_id),
            summary=f"Organisation cancelled; erasure scheduled after {tenant.erase_after.date().isoformat()}",
            meta={"users_disabled": len(users), "erase_after": tenant.erase_after.isoformat()},
        )
        await session.flush()
        return TenantDeleteResult(
            status=tenant.status, cancelled_at=now, erase_after=tenant.erase_after, users_disabled=len(users),
        )
