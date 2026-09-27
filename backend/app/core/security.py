"""Security primitives: password hashing, JWT issuance/verification, MFA.

- Passwords are hashed with **Argon2id** (memory-hard, OWASP-recommended).
- Access tokens are short-lived JWTs; refresh tokens are opaque, rotated, and
  stored hashed (see the identity module). This file only handles the crypto.
- Supports symmetric (HS256, dev) and asymmetric (RS256/ES256, prod) signing.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

# Argon2id parameters tuned per OWASP guidance (>= 19 MiB, t=2, p=1).
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


# ─── Password hashing ───────────────────────────────────────────────
def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _password_hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(hashed: str) -> bool:
    """True if the stored hash used weaker params than current policy."""
    try:
        return _password_hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


# ─── JWT signing keys ───────────────────────────────────────────────
@lru_cache
def _signing_key() -> str:
    if settings.JWT_ALGORITHM == "HS256":
        return settings.SECRET_KEY
    if not settings.JWT_PRIVATE_KEY_PATH:
        raise RuntimeError("Asymmetric JWT requires VS_JWT_PRIVATE_KEY_PATH.")
    return Path(settings.JWT_PRIVATE_KEY_PATH).read_text()


@lru_cache
def _verification_key() -> str:
    if settings.JWT_ALGORITHM == "HS256":
        return settings.SECRET_KEY
    if not settings.JWT_PUBLIC_KEY_PATH:
        raise RuntimeError("Asymmetric JWT requires VS_JWT_PUBLIC_KEY_PATH.")
    return Path(settings.JWT_PUBLIC_KEY_PATH).read_text()


# ─── JWT issuance & verification ────────────────────────────────────
def create_access_token(
    *,
    subject: str,
    tenant_id: str | None,
    scopes: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed short-lived access token.

    ``subject`` is the user id. ``tenant_id`` scopes the token to a tenant so a
    stolen token cannot be replayed against another tenant.
    """
    now = datetime.now(UTC)
    expire = now + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    claims: dict[str, Any] = {
        "sub": subject,
        "tid": tenant_id,
        "type": TokenType.ACCESS.value,
        "scopes": scopes or [],
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": uuid4().hex,
        "iss": settings.PROJECT_NAME,
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, _signing_key(), algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Decode and validate a JWT. Raises ``jwt.PyJWTError`` on any failure."""
    payload: dict[str, Any] = jwt.decode(
        token,
        _verification_key(),
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.PROJECT_NAME,
        options={"require": ["exp", "sub", "type"]},
    )
    if expected_type and payload.get("type") != expected_type.value:
        raise jwt.InvalidTokenError(
            f"Expected {expected_type.value} token, got {payload.get('type')}"
        )
    return payload


# ─── Refresh tokens (opaque, stored hashed) ─────────────────────────
def generate_refresh_token() -> str:
    """A high-entropy opaque refresh token (never a JWT)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Deterministic hash for at-rest storage & constant-time lookup."""
    return hashlib.sha256(f"{settings.SECRET_KEY}:{token}".encode()).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


# ─── One-time / verification codes ──────────────────────────────────
def generate_numeric_otp(length: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def generate_url_safe_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)
