"""Passkey (WebAuthn) service — registration & authentication ceremonies.

Registration adds a passkey to an authenticated user's account; authentication
is a pre-login ceremony that resolves a user by email, verifies an assertion
against a stored credential, and issues our token pair. Cryptographic
verification is delegated to the pluggable :mod:`app.core.webauthn` verifier.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.webauthn import get_webauthn_verifier
from app.modules.audit.service import record_audit
from app.modules.identity.models import User, WebAuthnChallenge, WebAuthnCredential
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import CurrentUser, TokenPair
from app.modules.identity.service import AuthService

_CHALLENGE_TTL_MINUTES = 5


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class PasskeyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.verifier = get_webauthn_verifier()
        self.users = UserRepository(session)
        self.auth = AuthService(session)

    async def _new_challenge(self, *, user_id: uuid.UUID | None, kind: str) -> str:
        challenge = secrets.token_urlsafe(32)
        self.session.add(
            WebAuthnChallenge(
                challenge=challenge,
                user_id=user_id,
                kind=kind,
                expires_at=datetime.now(UTC) + timedelta(minutes=_CHALLENGE_TTL_MINUTES),
                consumed=False,
            )
        )
        await self.session.flush()
        return challenge

    async def _consume_challenge(self, *, kind: str, user_id: uuid.UUID | None) -> WebAuthnChallenge:
        stmt = (
            select(WebAuthnChallenge)
            .where(
                WebAuthnChallenge.kind == kind,
                WebAuthnChallenge.consumed.is_(False),
            )
            .order_by(WebAuthnChallenge.created_at.desc())
        )
        if user_id is not None:
            stmt = stmt.where(WebAuthnChallenge.user_id == user_id)
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None or _as_utc(row.expires_at) < datetime.now(UTC):
            raise AuthenticationError("No pending passkey challenge, or it has expired.")
        row.consumed = True
        return row

    async def _credentials(self, user_id: uuid.UUID) -> list[WebAuthnCredential]:
        res = await self.session.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.user_id == user_id,
                WebAuthnCredential.deleted_at.is_(None),
            )
        )
        return list(res.scalars().all())

    # ─── Registration (authenticated) ───────────────────────────────
    async def register_begin(self, current: CurrentUser) -> dict:
        existing = await self._credentials(current.id)
        challenge = await self._new_challenge(user_id=current.id, kind="registration")
        return self.verifier.registration_options(
            challenge=challenge,
            user_id=str(current.id),
            user_name=current.email,
            exclude_ids=[c.credential_id for c in existing],
        )

    async def register_finish(
        self, current: CurrentUser, name: str, response: dict
    ) -> WebAuthnCredential:
        row = await self._consume_challenge(kind="registration", user_id=current.id)
        verified = self.verifier.verify_registration(challenge=row.challenge, response=response)
        dupe = await self.session.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.credential_id == verified.credential_id
            )
        )
        if dupe.scalar_one_or_none() is not None:
            raise ConflictError("This passkey is already registered.")
        credential = WebAuthnCredential(
            tenant_id=current.tenant_id,
            user_id=current.id,
            credential_id=verified.credential_id,
            public_key=verified.public_key,
            sign_count=verified.sign_count,
            name=name,
        )
        self.session.add(credential)
        await self.session.flush()
        self._audit(current, "auth.passkey_added", f"Registered passkey '{name}'", credential)
        return credential

    def _audit(self, current: CurrentUser, action: str, summary: str, credential: WebAuthnCredential) -> None:
        if current.tenant_id is None:
            return
        record_audit(
            self.session,
            tenant_id=current.tenant_id,
            actor_id=current.id,
            actor_label=current.email,
            action=action,
            summary=summary,
            entity_type="passkey",
            entity_id=str(credential.id),
        )

    async def list(self, current: CurrentUser) -> list[WebAuthnCredential]:
        return await self._credentials(current.id)

    async def delete(self, current: CurrentUser, credential_pk: uuid.UUID) -> None:
        res = await self.session.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.id == credential_pk,
                WebAuthnCredential.user_id == current.id,
                WebAuthnCredential.deleted_at.is_(None),
            )
        )
        credential = res.scalar_one_or_none()
        if credential is None:
            raise NotFoundError("Passkey not found.")
        credential.deleted_at = datetime.now(UTC)
        self._audit(current, "auth.passkey_removed", f"Removed passkey '{credential.name}'", credential)

    # ─── Authentication (pre-login) ─────────────────────────────────
    async def authenticate_begin(self, email: str) -> dict:
        user = await self._resolve_user(email)
        credentials = await self._credentials(user.id)
        if not credentials:
            raise NotFoundError("No passkey is registered for this account.")
        challenge = await self._new_challenge(user_id=user.id, kind="authentication")
        return self.verifier.authentication_options(
            challenge=challenge, allow_ids=[c.credential_id for c in credentials]
        )

    async def authenticate_finish(
        self, response: dict, *, ip: str | None = None, user_agent: str | None = None
    ) -> TokenPair:
        credential_id = response.get("credential_id")
        if not credential_id:
            raise AuthenticationError("Malformed passkey assertion.")
        res = await self.session.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.credential_id == credential_id,
                WebAuthnCredential.deleted_at.is_(None),
            )
        )
        credential = res.scalar_one_or_none()
        if credential is None:
            raise AuthenticationError("Unknown passkey.")

        row = await self._consume_challenge(kind="authentication", user_id=credential.user_id)
        new_count = self.verifier.verify_authentication(
            challenge=row.challenge,
            response=response,
            public_key=credential.public_key,
            sign_count=credential.sign_count,
        )
        credential.sign_count = new_count
        credential.last_used_at = datetime.now(UTC)

        user = await self.users.get_by_id_global(credential.user_id)
        if user is None or not user.is_active:
            raise PermissionDeniedError("This account is unavailable.")
        user.last_login_at = datetime.now(UTC)
        user.failed_login_count = 0
        user.locked_until = None
        record_audit(
            self.session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_label=user.email,
            action="auth.login",
            summary="Signed in with a passkey",
            entity_type="user",
            entity_id=str(user.id),
            meta={"ip": ip, "passkey": credential.name},
        )
        return await self.auth.issue_tokens_for_user(
            user, ip=ip, user_agent=user_agent, label="passkey"
        )

    async def _resolve_user(self, email: str) -> User:
        candidates = await self.users.find_by_email_global(email)
        if not candidates:
            raise NotFoundError("No passkey is registered for this account.")
        if len(candidates) > 1:
            raise ConflictError("This email is associated with multiple organisations.")
        return candidates[0]
