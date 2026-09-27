"""API-key service: issuance, listing, revocation, and authentication.

A key acts *as its creator* with a subset of the creator's permissions. That
relationship is re-validated on every use (audit A-19): a key dies with its
creator (deactivated, deleted, moved tenant) and can never grant a scope the
creator no longer holds — the stored scopes are intersected with the creator's
current permission codes at authentication time.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, NotFoundError, ValidationError
from app.modules.apikeys.models import ApiKey
from app.modules.apikeys.repository import ApiKeyRepository
from app.modules.identity.rbac import ALL_PERMISSION_CODES
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import CurrentUser

_KEY_PREFIX = "vsk_"
_PREFIX_DISPLAY_LEN = 12
MAX_KEY_LIFETIME_DAYS = 365


def hash_key(raw: str) -> str:
    """API keys are high-entropy, so a fast SHA-256 (not bcrypt) is appropriate."""
    return hashlib.sha256(raw.encode()).hexdigest()


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def authenticate_api_key(session: AsyncSession, raw_token: str) -> CurrentUser:
    """Resolve an ``vsk_`` bearer token to a principal, or raise. Runs on a
    bypass-RLS session (pre-tenant). The principal acts AS the key's creator but
    with only the key's scopes ∩ the creator's *current* permissions."""
    key = await ApiKeyRepository(session).get_by_hash(hash_key(raw_token))
    if key is None or key.revoked:
        raise AuthenticationError("Invalid API key.")
    if key.expires_at is not None and _as_utc(key.expires_at) < datetime.now(UTC):
        raise AuthenticationError("This API key has expired.")
    creator = await UserRepository(session).get_by_id_global(key.created_by)
    if (
        creator is None
        or not creator.is_active
        or creator.deleted_at is not None
        or creator.tenant_id != key.tenant_id
    ):
        raise AuthenticationError("This API key is no longer valid (its owner cannot sign in).")
    allowed = set(ALL_PERMISSION_CODES) if creator.is_superuser else creator.permission_codes
    scopes = [s for s in (key.scopes or []) if s in allowed]
    key.last_used_at = datetime.now(UTC)
    return CurrentUser(
        id=key.created_by,
        tenant_id=key.tenant_id,
        email=f"apikey:{key.name}",
        is_superuser=False,
        scopes=scopes,
        token_epoch=creator.token_epoch or 0,
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
        if expires_at is None:
            raise ValidationError("An expiry date is required for API keys.")
        now = datetime.now(UTC)
        expires_at = _as_utc(expires_at)
        if expires_at <= now:
            raise ValidationError("The expiry date must be in the future.")
        if expires_at > now + timedelta(days=MAX_KEY_LIFETIME_DAYS):
            raise ValidationError(f"API keys may live at most {MAX_KEY_LIFETIME_DAYS} days.")
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
