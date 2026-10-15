"""Which client sent this request: the website or the VidhiSangh phone app.

The app sends ``X-VidhiSangh-Client: app``. App sessions last longer and
tolerate a lost refresh response: on a phone the refresh token sits in the
app's own cookie store, and the person expects to stay signed in until they
sign out, even after days offline or on a weak network. The header can only
lengthen the sender's own session, so it needs no proof.
"""

from __future__ import annotations

from contextvars import ContextVar

from app.core.config import settings

APP_CLIENT_HEADER = "x-vidhisangh-client"
_is_app: ContextVar[bool] = ContextVar("vs_is_app_client", default=False)


def set_app_client(value: bool) -> None:
    _is_app.set(value)


def is_app_client() -> bool:
    return _is_app.get()


def refresh_token_days() -> int:
    return settings.REFRESH_TOKEN_EXPIRE_DAYS_APP if is_app_client() else settings.REFRESH_TOKEN_EXPIRE_DAYS


def refresh_reuse_grace_seconds() -> int:
    return settings.REFRESH_REUSE_GRACE_SECONDS_APP if is_app_client() else settings.REFRESH_REUSE_GRACE_SECONDS
