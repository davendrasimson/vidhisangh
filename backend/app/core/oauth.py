"""OAuth 2.0 / OIDC sign-in seam.

Providers are configured from the environment (``VS_OAUTH_<NAME>_CLIENT_ID`` /
``_CLIENT_SECRET``); a provider is only offered once its credentials are present.
A built-in ``mock`` provider exists for dev/CI so the full authorization-code
flow is exercisable without real IdP credentials. It is a complete sign-in
bypass, so it is offered **only** when ``VS_OAUTH_MOCK_ENABLED=true`` *and* the
environment is not production (start-up refuses the combination; audit A-8).

The token-exchange + userinfo + id-token verification calls go through a
pluggable ``OAuthClient`` (real httpx/PyJWT by default) so the real-provider
path stays swappable; the ``mock`` provider synthesises identity locally and
never makes a network call.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import httpx
import jwt

from app.core.config import settings

MOCK_PROVIDER = "mock"


@dataclass(slots=True)
class OAuthUserInfo:
    provider: str
    subject: str
    email: str
    email_verified: bool
    name: str | None = None
    # True when the identity came from a verified OIDC id_token (signature, aud,
    # iss, exp, nonce all checked) rather than from the userinfo endpoint alone.
    from_id_token: bool = False


@dataclass(slots=True)
class OAuthTokens:
    access_token: str
    id_token: str | None = None


@dataclass(slots=True)
class OAuthProviderConfig:
    name: str
    display_name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str] = field(default_factory=list)
    jwks_url: str | None = None
    issuers: tuple[str, ...] = ()  # exact issuer values, or prefixes ending in "*"

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


# Static endpoint metadata for the built-in providers. Credentials come from env.
_PROVIDER_META: dict[str, dict] = {
    "google": {
        "display_name": "Google",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "jwks_url": "https://www.googleapis.com/oauth2/v3/certs",
        "issuers": ("https://accounts.google.com", "accounts.google.com"),
        "scopes": ["openid", "email", "profile"],
    },
    "microsoft": {
        "display_name": "Microsoft",
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/oidc/userinfo",
        "jwks_url": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
        # Issuer carries the directory tenant id: https://login.microsoftonline.com/<tid>/v2.0
        "issuers": ("https://login.microsoftonline.com/*",),
        "scopes": ["openid", "email", "profile"],
    },
    "linkedin": {
        "display_name": "LinkedIn",
        "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "userinfo_url": "https://api.linkedin.com/v2/userinfo",
        "jwks_url": "https://www.linkedin.com/oauth/openid/jwks",
        "issuers": ("https://www.linkedin.com/oauth", "https://www.linkedin.com"),
        "scopes": ["openid", "email", "profile"],
    },
}


def mock_provider_enabled() -> bool:
    return bool(settings.OAUTH_MOCK_ENABLED) and not settings.is_production


def get_oauth_providers() -> dict[str, OAuthProviderConfig]:
    """Configured real providers, plus the ``mock`` provider when opted in."""
    providers: dict[str, OAuthProviderConfig] = {}
    for name, meta in _PROVIDER_META.items():
        client_id = _env(name, "CLIENT_ID")
        client_secret = _env(name, "CLIENT_SECRET")
        cfg = OAuthProviderConfig(
            name=name,
            display_name=meta["display_name"],
            client_id=client_id,
            client_secret=client_secret,
            authorize_url=meta["authorize_url"],
            token_url=meta["token_url"],
            userinfo_url=meta["userinfo_url"],
            scopes=meta["scopes"],
            jwks_url=meta.get("jwks_url"),
            issuers=tuple(meta.get("issuers", ())),
        )
        if cfg.configured:
            providers[name] = cfg
    if mock_provider_enabled():
        providers[MOCK_PROVIDER] = OAuthProviderConfig(
            name=MOCK_PROVIDER,
            display_name="Mock IdP (dev)",
            client_id="mock",
            client_secret="mock",
            authorize_url="urn:vidhisangh:mock:authorize",
            token_url="",
            userinfo_url="",
            scopes=["openid", "email"],
        )
    return providers


def _env(provider: str, suffix: str) -> str:
    import os

    return os.environ.get(f"VS_OAUTH_{provider.upper()}_{suffix}", "")


# ─── PKCE helpers ───────────────────────────────────────────────────
def generate_pkce() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for PKCE (S256)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def issuer_allowed(cfg: OAuthProviderConfig, iss: str | None) -> bool:
    if not iss:
        return False
    for allowed in cfg.issuers:
        if allowed.endswith("*"):
            if iss.startswith(allowed[:-1]):
                return True
        elif iss == allowed:
            return True
    return False


# ─── Transport for real providers ───────────────────────────────────
@runtime_checkable
class OAuthClient(Protocol):
    async def exchange_code(
        self, cfg: OAuthProviderConfig, *, code: str, code_verifier: str, redirect_uri: str
    ) -> OAuthTokens: ...

    async def fetch_userinfo(self, cfg: OAuthProviderConfig, *, access_token: str) -> OAuthUserInfo: ...

    async def verify_id_token(
        self, cfg: OAuthProviderConfig, *, id_token: str, nonce: str
    ) -> dict: ...


class IdTokenError(ValueError):
    """The provider's id_token failed verification (signature/aud/iss/exp/nonce)."""


class HttpxOAuthClient:
    async def exchange_code(
        self, cfg: OAuthProviderConfig, *, code: str, code_verifier: str, redirect_uri: str
    ) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                cfg.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": cfg.client_id,
                    "client_secret": cfg.client_secret,
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            body = resp.json()
            return OAuthTokens(access_token=body["access_token"], id_token=body.get("id_token"))

    async def fetch_userinfo(
        self, cfg: OAuthProviderConfig, *, access_token: str
    ) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                cfg.userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
            )
            resp.raise_for_status()
            data = resp.json()
        return OAuthUserInfo(
            provider=cfg.name,
            subject=str(data.get("sub") or data.get("id") or ""),
            email=(data.get("email") or "").lower(),
            # Never assume: a provider that omits the claim has not verified it.
            email_verified=_truthy(data.get("email_verified")),
            name=data.get("name"),
        )

    async def verify_id_token(
        self, cfg: OAuthProviderConfig, *, id_token: str, nonce: str
    ) -> dict:
        """Verify signature (provider JWKS), audience, issuer, expiry and nonce."""
        if not cfg.jwks_url:
            raise IdTokenError("No JWKS endpoint configured for this provider.")
        try:
            key = jwt.PyJWKClient(cfg.jwks_url, cache_keys=True).get_signing_key_from_jwt(id_token).key
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256", "ES256"],
                audience=cfg.client_id,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
                leeway=60,
            )
        except jwt.PyJWTError as exc:
            raise IdTokenError(f"id_token rejected: {exc}") from exc
        if not issuer_allowed(cfg, claims.get("iss")):
            raise IdTokenError("id_token issuer is not recognised for this provider.")
        if claims.get("nonce") != nonce:
            raise IdTokenError("id_token nonce mismatch.")
        return claims


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


_client: OAuthClient | None = None


def get_oauth_client() -> OAuthClient:
    global _client
    if _client is None:
        _client = HttpxOAuthClient()
    return _client


def set_oauth_client(client: OAuthClient | None) -> None:
    global _client
    _client = client
