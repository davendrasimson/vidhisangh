"""OAuth / OIDC sign-in service.

Implements the authorization-code + PKCE flow: ``authorize`` mints a signed
state row and returns the provider URL; ``callback`` validates the state,
resolves the external identity to an existing VidhiSangh user (matched by
verified email), and issues our own token pair. SSO signs in **existing**
accounts only — provisioning is done by an admin invite.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.oauth import (
    MOCK_PROVIDER,
    OAuthUserInfo,
    generate_pkce,
    get_oauth_client,
    get_oauth_providers,
)
from app.modules.audit.service import record_audit
from app.modules.identity.models import OAuthState, User
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import TokenPair
from app.modules.identity.service import AuthService

_STATE_TTL_MINUTES = 10


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class OAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.auth = AuthService(session)

    def list_providers(self) -> list[dict]:
        return [
            {"name": cfg.name, "display_name": cfg.display_name}
            for cfg in get_oauth_providers().values()
        ]

    async def authorize(
        self, provider: str, redirect_uri: str, login_hint: str | None
    ) -> dict:
        cfg = get_oauth_providers().get(provider)
        if cfg is None:
            raise NotFoundError("Unknown or unconfigured OAuth provider.")

        state = secrets.token_urlsafe(24)
        verifier, challenge = generate_pkce()
        nonce = secrets.token_urlsafe(16)
        self.session.add(
            OAuthState(
                state=state,
                provider=provider,
                code_verifier=verifier,
                redirect_uri=redirect_uri,
                login_hint=login_hint,
                nonce=nonce,
                expires_at=datetime.now(UTC) + timedelta(minutes=_STATE_TTL_MINUTES),
                consumed=False,
            )
        )
        await self.session.flush()

        if provider == MOCK_PROVIDER:
            # No real IdP: point straight back at the app's callback route.
            sep = "&" if "?" in redirect_uri else "?"
            authorize_url = f"{redirect_uri}{sep}code=mock-{state[:8]}&state={state}"
        else:
            params = {
                "response_type": "code",
                "client_id": cfg.client_id,
                "redirect_uri": redirect_uri,
                "scope": " ".join(cfg.scopes),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "nonce": nonce,
            }
            if login_hint:
                params["login_hint"] = login_hint
            authorize_url = f"{cfg.authorize_url}?{urlencode(params)}"
        return {"authorize_url": authorize_url, "state": state}

    async def callback(
        self,
        provider: str,
        code: str,
        state: str,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> TokenPair:
        cfg = get_oauth_providers().get(provider)
        if cfg is None:
            raise NotFoundError("Unknown or unconfigured OAuth provider.")

        row = (
            await self.session.execute(select(OAuthState).where(OAuthState.state == state))
        ).scalar_one_or_none()
        if row is None or row.provider != provider or row.consumed:
            raise AuthenticationError("Invalid or already-used sign-in request.")
        if _as_utc(row.expires_at) < datetime.now(UTC):
            raise AuthenticationError("This sign-in request has expired.")
        row.consumed = True

        info = await self._resolve_identity(provider, cfg, code, row)
        if not info.email:
            raise AuthenticationError("The identity provider did not return an email address.")
        if not info.email_verified:
            raise AuthenticationError("Your email address is not verified with the provider.")

        user = await self._resolve_user(info.email)
        user.last_login_at = datetime.now(UTC)
        user.failed_login_count = 0
        user.locked_until = None
        record_audit(
            self.session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_label=user.email,
            action="auth.sso_login",
            summary=f"Signed in via {cfg.display_name}",
            entity_type="user",
            entity_id=str(user.id),
        )
        return await self.auth.issue_tokens_for_user(
            user, ip=ip, user_agent=user_agent, label=f"sso:{provider}"
        )

    async def _resolve_identity(self, provider, cfg, code, row: OAuthState) -> OAuthUserInfo:
        if provider == MOCK_PROVIDER:
            if not row.login_hint:
                raise AuthenticationError("Mock sign-in requires a login_hint email.")
            return OAuthUserInfo(
                provider=provider,
                subject=row.login_hint.lower(),
                email=row.login_hint.lower(),
                email_verified=True,
                name=None,
            )
        client = get_oauth_client()
        access_token = await client.exchange_code(
            cfg, code=code, code_verifier=row.code_verifier, redirect_uri=row.redirect_uri
        )
        return await client.fetch_userinfo(cfg, access_token=access_token)

    async def _resolve_user(self, email: str) -> User:
        candidates = await self.users.find_by_email_global(email)
        if not candidates:
            raise PermissionDeniedError(
                "No VidhiSangh account is linked to this email. Ask your administrator to invite you."
            )
        # Emails are unique platform-wide (users_email_global_unique), so this
        # is always a single account — SSO no longer has an ambiguous case.
        user = candidates[0]
        if not user.is_active:
            raise PermissionDeniedError("This account is disabled.")
        return user
