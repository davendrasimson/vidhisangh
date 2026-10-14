"""OAuth / OIDC sign-in service.

Implements the authorization-code + PKCE flow: ``authorize`` mints a signed
state row and returns the provider URL; ``callback`` validates the state,
resolves the external identity to a VidhiSangh user, and issues our own token
pair. A verified email with no account behind it creates an individual account
(sign-up with Google) unless ``OAUTH_SIGNUP_ENABLED`` is off.

Identity resolution (audit A-21):
1. A verified OIDC ``id_token`` (signature via the provider's JWKS, ``aud``,
   ``iss``, ``exp``, ``nonce``) is the preferred source of ``sub``/``email``.
   Without one, the userinfo endpoint must itself report ``email_verified``.
2. ``(provider, subject)`` is matched against ``oauth_identities`` first.
3. Only when no link exists yet is the (verified) email used to find the
   account, and the link is recorded so future sign-ins do not depend on the
   email at all.
4. ``redirect_uri`` must belong to the app's own origin (``PUBLIC_APP_URL``,
   CORS origins, ``OAUTH_ALLOWED_REDIRECT_ORIGINS``).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.oauth import (
    MOCK_PROVIDER,
    IdTokenError,
    OAuthProviderConfig,
    OAuthUserInfo,
    generate_pkce,
    get_oauth_client,
    get_oauth_providers,
)
from app.modules.audit.service import record_audit
from app.modules.identity.models import OAuthIdentity, OAuthState, User
from app.modules.identity.repository import OAuthIdentityRepository, UserRepository
from app.modules.identity.schemas import TokenPair
from app.modules.identity.service import AuthService

_STATE_TTL_MINUTES = 10


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def redirect_uri_allowed(redirect_uri: str) -> bool:
    try:
        parts = urlsplit(redirect_uri)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.fragment:
        return False
    origin = f"{parts.scheme}://{parts.netloc}".lower()
    return origin in {o.lower() for o in settings.oauth_allowed_redirect_origins}


class OAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.identities = OAuthIdentityRepository(session)
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
        if not redirect_uri_allowed(redirect_uri):
            raise ValidationError("redirect_uri must point at the VidhiSangh application.")

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
        referral_code: str | None = None,
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
        # Commit the consumption before any fallible work (network calls,
        # identity checks): a failure must not hand the state back (audit A-23).
        await self.session.commit()

        info = await self._resolve_identity(provider, cfg, code, row)
        if not info.subject:
            raise AuthenticationError("The identity provider did not return a stable subject.")

        user = await self._resolve_user(provider, info)
        if user is None:
            created, pair = await self._sign_up(cfg, info, ip=ip, user_agent=user_agent,
                                                referral_code=referral_code)
            created.last_login_at = datetime.now(UTC)
            assert pair is not None  # the provider verified the email
            pair.new_account = True
            return pair
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
            meta={"ip": ip, "provider": provider, "id_token": info.from_id_token},
        )
        return await self.auth.issue_tokens_for_user(
            user, ip=ip, user_agent=user_agent, label=f"sso:{provider}"
        )

    async def _resolve_identity(
        self, provider: str, cfg: OAuthProviderConfig, code: str, row: OAuthState
    ) -> OAuthUserInfo:
        if provider == MOCK_PROVIDER:
            if not row.login_hint:
                raise AuthenticationError("Mock sign-in requires a login_hint email.")
            return OAuthUserInfo(
                provider=provider,
                subject=f"mock:{row.login_hint.lower()}",
                email=row.login_hint.lower(),
                email_verified=True,
                name=None,
            )
        client = get_oauth_client()
        tokens = await client.exchange_code(
            cfg, code=code, code_verifier=row.code_verifier, redirect_uri=row.redirect_uri
        )
        info = await client.fetch_userinfo(cfg, access_token=tokens.access_token)
        if tokens.id_token:
            try:
                claims = await client.verify_id_token(cfg, id_token=tokens.id_token, nonce=row.nonce)
            except IdTokenError as exc:
                raise AuthenticationError(str(exc)) from exc
            # The verified token is authoritative for identity claims.
            info.subject = str(claims.get("sub") or info.subject)
            if claims.get("email"):
                info.email = str(claims["email"]).lower()
            if "email_verified" in claims:
                ev = claims["email_verified"]
                info.email_verified = ev if isinstance(ev, bool) else str(ev).lower() == "true"
            info.from_id_token = True
        return info

    async def _sign_up(
        self, cfg: OAuthProviderConfig, info: OAuthUserInfo, *, ip: str | None,
        user_agent: str | None, referral_code: str | None,
    ) -> tuple[User, TokenPair | None]:
        """An individual account for a provider-verified email, linked to the identity."""
        from app.modules.identity.schemas import RegisterRequest

        assert info.email
        name = " ".join((info.name or "").split())[:200]
        if len(name) < 2:
            name = info.email.split("@", 1)[0][:200]
        registration = RegisterRequest.model_construct(
            organisation_name=name, practice_type="individual", full_name=name,
            email=info.email, phone=None,
            # Never shown: they sign in with Google, or set one via "Forgot password".
            password=secrets.token_urlsafe(24) + "aA1!",
            # The sign-up button states that continuing accepts the Terms and Privacy Notice.
            accept_terms=True, add_sample_data=False, device_id=None,
            referral_code=referral_code, professional_role=None, role_visibility="everyone",
        )
        user, pair = await self.auth.register(
            registration, ip=ip, user_agent=user_agent, verified_email=True
        )
        self.identities.add(OAuthIdentity(
            user_id=user.id, provider=cfg.name, subject=info.subject, email=info.email,
            last_used_at=datetime.now(UTC),
        ))
        record_audit(
            self.session, tenant_id=user.tenant_id, actor_id=user.id, actor_label=user.email,
            action="auth.sso_signup", summary=f"Created the account with {cfg.display_name}",
            entity_type="user", entity_id=str(user.id), meta={"ip": ip, "provider": cfg.name},
        )
        await self.session.flush()
        return user, pair

    async def _resolve_user(self, provider: str, info: OAuthUserInfo) -> User | None:
        """The linked or same-email account; ``None`` when a new one may be created."""
        identity = await self.identities.get(provider, info.subject)
        if identity is not None:
            user = await self.users.get_by_id_global(identity.user_id)
            if user is None:
                raise PermissionDeniedError("The linked VidhiSangh account no longer exists.")
            if not user.is_active:
                raise PermissionDeniedError("This account is disabled.")
            identity.last_used_at = datetime.now(UTC)
            identity.email = info.email or identity.email
            return user

        # First sign-in with this provider: the email may establish the link,
        # but only when the provider vouches for it.
        if not info.email:
            raise AuthenticationError("The identity provider did not return an email address.")
        if not info.email_verified:
            raise AuthenticationError("Your email address is not verified with the provider.")
        candidates = await self.users.find_by_email_global(info.email)
        if not candidates and settings.OAUTH_SIGNUP_ENABLED:
            return None
        if not candidates:
            raise PermissionDeniedError(
                "No VidhiSangh account is linked to this email. Ask your administrator to invite you."
            )
        # Emails are unique platform-wide (users_email_global_unique), so this
        # is always a single account — SSO no longer has an ambiguous case.
        user = candidates[0]
        if not user.is_active:
            raise PermissionDeniedError("This account is disabled.")
        self.identities.add(
            OAuthIdentity(
                user_id=user.id,
                provider=provider,
                subject=info.subject,
                email=info.email,
                last_used_at=datetime.now(UTC),
            )
        )
        record_audit(
            self.session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_label=user.email,
            action="auth.sso_linked",
            summary=f"Linked {provider} identity to the account",
            entity_type="user",
            entity_id=str(user.id),
            meta={"provider": provider},
        )
        return user
