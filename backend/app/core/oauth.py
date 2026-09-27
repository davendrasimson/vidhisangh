"""OAuth 2.0 / OIDC sign-in seam.

Providers are configured from the environment (``VS_OAUTH_<NAME>_CLIENT_ID`` /
``_CLIENT_SECRET``); a provider is only offered once its credentials are present.
A built-in ``mock`` provider is available OUTSIDE production so the full
authorization-code flow is exercisable in dev/CI without real IdP credentials.

The token-exchange + userinfo HTTP calls go through a pluggable ``OAuthClient``
(real httpx by default) so the real-provider path stays swappable; the ``mock``
provider synthesises identity locally and never makes a network call.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import httpx

from app.core.config import settings

MOCK_PROVIDER = "mock"


@dataclass(slots=True)
class OAuthUserInfo:
    provider: str
    subject: str
    email: str
    email_verified: bool
    name: str | None = None


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
        "scopes": ["openid", "email", "profile"],
    },
    "microsoft": {
        "display_name": "Microsoft",
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/oidc/userinfo",
        "scopes": ["openid", "email", "profile"],
    },
    "linkedin": {
        "display_name": "LinkedIn",
        "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "userinfo_url": "https://api.linkedin.com/v2/userinfo",
        "scopes": ["openid", "email", "profile"],
    },
}


def get_oauth_providers() -> dict[str, OAuthProviderConfig]:
    """Configured real providers, plus the ``mock`` provider outside production."""
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
        )
        if cfg.configured:
            providers[name] = cfg
    if not settings.is_production:
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


# ─── Transport for real providers ───────────────────────────────────
@runtime_checkable
class OAuthClient(Protocol):
    async def exchange_code(
        self, cfg: OAuthProviderConfig, *, code: str, code_verifier: str, redirect_uri: str
    ) -> str: ...

    async def fetch_userinfo(self, cfg: OAuthProviderConfig, *, access_token: str) -> OAuthUserInfo: ...


class HttpxOAuthClient:
    async def exchange_code(
        self, cfg: OAuthProviderConfig, *, code: str, code_verifier: str, redirect_uri: str
    ) -> str:
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
            return resp.json()["access_token"]

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
            subject=str(data.get("sub") or data.get("id") or data.get("email", "")),
            email=(data.get("email") or "").lower(),
            email_verified=bool(data.get("email_verified", True)),
            name=data.get("name"),
        )


_client: OAuthClient | None = None


def get_oauth_client() -> OAuthClient:
    global _client
    if _client is None:
        _client = HttpxOAuthClient()
    return _client


def set_oauth_client(client: OAuthClient | None) -> None:
    global _client
    _client = client
