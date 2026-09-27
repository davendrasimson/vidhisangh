"""Feature-flag service: resolve the catalog against a tenant's overrides."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.featureflags.catalog import CATALOG_BY_KEY, FLAG_CATALOG, FLAG_KEYS
from app.modules.featureflags.models import FeatureFlag
from app.modules.featureflags.repository import FeatureFlagRepository


class FeatureFlagService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.repo = FeatureFlagRepository(session)

    async def list_flags(self) -> list[dict]:
        """Every catalog flag merged with this tenant's overrides."""
        overrides = {f.key: f for f in await self.repo.list(self.tenant_id)}
        result: list[dict] = []
        for flag in FLAG_CATALOG:
            override = overrides.get(flag.key)
            result.append(
                {
                    "key": flag.key,
                    "name": flag.name,
                    "description": flag.description,
                    "enabled": override.enabled if override else flag.default,
                    "default": flag.default,
                    "overridden": override is not None,
                }
            )
        return result

    async def resolve(self) -> dict[str, bool]:
        """The effective on/off map for the tenant (for app/frontend gating)."""
        overrides = {f.key: f.enabled for f in await self.repo.list(self.tenant_id)}
        return {flag.key: overrides.get(flag.key, flag.default) for flag in FLAG_CATALOG}

    async def is_enabled(self, key: str) -> bool:
        if key not in FLAG_KEYS:
            raise NotFoundError(f"Unknown feature flag '{key}'.")
        override = await self.repo.get(self.tenant_id, key)
        return override.enabled if override else CATALOG_BY_KEY[key].default

    async def set_flag(self, key: str, enabled: bool) -> dict:
        if key not in FLAG_KEYS:
            raise NotFoundError(f"Unknown feature flag '{key}'.")
        flag = await self.repo.get(self.tenant_id, key)
        if flag is None:
            flag = FeatureFlag(tenant_id=self.tenant_id, key=key, enabled=enabled, updated_by=self.user_id)
            self.repo.add(flag)
        else:
            flag.enabled = enabled
            flag.updated_by = self.user_id
        await self.session.flush()
        definition = CATALOG_BY_KEY[key]
        return {
            "key": key,
            "name": definition.name,
            "description": definition.description,
            "enabled": flag.enabled,
            "default": definition.default,
            "overridden": True,
        }
