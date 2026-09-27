"""API-key service: issuance, listing, revocation, and authentication."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, NotFoundError, ValidationError
from app.modules.apikeys.models import ApiKey
from app.modules.apikeys.repository import ApiKeyRepository
from app.modules.identity.rbac import ALL_PERMISSION_CODES
from app.modules.identity.schemas import CurrentUser

_KEY_PREFIX = "vsk_"
_PREFIX_DISPLAY_LEN = 12


def hash_key(raw: str) -> str:
    """API keys are high-entropy, so a fast SHA-256 (not bcrypt) is appropriate."""
    return hashlib.sha256(raw.encode()).hexdigest()


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def authenticate_api_key(session: AsyncSession, raw_token: str) -> CurrentUser:
    """Resolve an ``vsk_`` bearer token to a principal, or raise. Runs on a
    bypass-RLS session (pre-tenant). The principal acts AS the key's creator but
    with only the key's scopes."""
    key = await ApiKeyRepository(session).get_by_hash(hash_key(raw_token))
    if key is None or key.revoked:
        raise AuthenticationError("Invalid API key.")
    if key.expires_at is not None and _as_utc(key.expires_at) < datetime.now(UTC):
        raise AuthenticationError("This API key has expired.")
    key.last_used_at = datetime.now(UTC)
    return CurrentUser(
        id=key.created_by,
        tenant_id=key.tenant_id,
        email=f"apikey:{key.name}",
        is_superuser=False,
        scopes=list(key.scopes or []),
    )


class ApiKeyService:
    def __init__(self, session: AsyncSession, current: CurrentUser) -> None:
        self.session = session
        self.current = current
        self.tenant_id = current.tenant_id
        self.repo = ApiKeyRepository(session)

    def _grantable(self) -> set[str]:
        if self.current.is_superuser or "*" in self.current.scopes:
            return set(ALL_PERMISSION_CODES)
        return set(self.current.scopes)

    def available_scopes(self) -> list[str]:
        return sorted(self._grantable())

    async def create(
        self, *, name: str, scopes: list[str], expires_at: datetime | None
    ) -> tuple[ApiKey, str]:
        grantable = self._grantable()
        requested = list(dict.fromkeys(scopes))  # dedupe, keep order
        forbidden = [s for s in requested if s not in grantable]
        if forbidden:
            raise ValidationError(
                f"You cannot grant scope(s) you don't hold: {', '.join(forbidden)}"
            )
        raw = _KEY_PREFIX + secrets.token_urlsafe(32)
        key = ApiKey(
            tenant_id=self.tenant_id,
            name=name,
            prefix=raw[:_PREFIX_DISPLAY_LEN],
            key_hash=hash_key(raw),
            scopes=requested,
            created_by=self.current.id,
            expires_at=expires_at,
            revoked=False,
        )
        self.repo.add(key)
        await self.session.flush()
        return key, raw

    async def list(self) -> list[ApiKey]:
        return await self.repo.list(self.tenant_id)

    async def revoke(self, key_id: uuid.UUID) -> ApiKey:
        key = await self.repo.get(self.tenant_id, key_id)
        if key is None:
            raise NotFoundError("API key not found.")
        key.revoked = True
        key.deleted_at = datetime.now(UTC)
        return key
