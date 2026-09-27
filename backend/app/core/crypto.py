"""Application-layer field encryption for PII / secrets at rest.

Provides symmetric encryption with **key rotation** and a SQLAlchemy
``TypeDecorator`` so sensitive columns (MFA secrets, tokens, PII) are encrypted
transparently before they touch the database.

Key management (audit A-7):

- ``VS_FIELD_ENCRYPTION_KEYS`` is a comma-separated list of Fernet keys,
  **newest first**. Keys are numbered from the oldest (``k1``) upwards, so
  prepending a new key never renumbers the old ones.
- Ciphertext is written as ``k<n>:<fernet token>``. Decryption tries the named
  key first, then every other configured key.
- A value **without** a prefix is legacy data encrypted with the Fernet key
  derived from ``SECRET_KEY``; it still decrypts, and is re-encrypted with the
  newest key the next time the row is written. When no explicit keys are
  configured, that derived key *is* the single (``k1``) key, so existing
  deployments keep working unchanged.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, TypeDecorator

from app.core.config import settings

_PREFIX = "k"


def _legacy_key() -> Fernet:
    """The pre-rotation key: derived from SECRET_KEY (what every existing row used)."""
    digest = hashlib.sha256(f"fieldcrypt:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


@lru_cache
def _keyring() -> dict[int, Fernet]:
    """``{key_id: Fernet}`` — id 1 is the oldest configured key."""
    raw = settings.field_encryption_keys
    if not raw:
        return {1: _legacy_key()}
    total = len(raw)
    ring: dict[int, Fernet] = {}
    for index, key in enumerate(raw):  # newest first → highest id
        try:
            ring[total - index] = Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                "VS_FIELD_ENCRYPTION_KEYS contains an invalid Fernet key "
                f"(entry {index + 1})."
            ) from exc
    return ring


@lru_cache
def _legacy() -> Fernet:
    return _legacy_key()


def current_key_id() -> int:
    return max(_keyring())


def reset_keyring() -> None:
    """Test hook: forget cached keys after settings change."""
    _keyring.cache_clear()
    _legacy.cache_clear()


def encrypt(plaintext: str) -> str:
    key_id = current_key_id()
    token = _keyring()[key_id].encrypt(plaintext.encode()).decode()
    return f"{_PREFIX}{key_id}:{token}"


def _split(ciphertext: str) -> tuple[int | None, str]:
    if ciphertext.startswith(_PREFIX):
        head, sep, rest = ciphertext.partition(":")
        if sep and head[1:].isdigit():
            return int(head[1:]), rest
    return None, ciphertext


def decrypt(ciphertext: str) -> str:
    key_id, token = _split(ciphertext)
    ring = _keyring()
    candidates: list[Fernet] = []
    if key_id is not None and key_id in ring:
        candidates.append(ring[key_id])
    candidates.extend(f for kid, f in sorted(ring.items(), reverse=True) if kid != key_id)
    if key_id is None:
        candidates.append(_legacy())  # un-prefixed value: SECRET_KEY-derived key
    data = token.encode()
    for fernet in candidates:
        try:
            return fernet.decrypt(data).decode()
        except InvalidToken:
            continue
    raise ValueError("Failed to decrypt field (key mismatch or corruption).")


def needs_reencryption(ciphertext: str) -> bool:
    """True when the value is not encrypted with the newest key."""
    key_id, _ = _split(ciphertext)
    return key_id != current_key_id()


class EncryptedString(TypeDecorator):
    """Transparently encrypt/decrypt a text column at the ORM boundary."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        return encrypt(value) if value is not None else None

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        return decrypt(value) if value is not None else None


# ─── Blind index (exact-match search over encrypted columns) ────────
# A ciphertext cannot be searched, so an HMAC-SHA256 of the *normalised*
# plaintext is stored beside it. The pepper is a secret separate from the
# encryption key (``VS_BLIND_INDEX_PEPPER``; derived from ``SECRET_KEY`` when
# unset) so the index leaks nothing without it — a plain hash of a 10-character
# PAN would be trivially brute-forced. Equality only: no prefix/ILIKE search.
@lru_cache
def _blind_index_pepper() -> bytes:
    pepper = getattr(settings, "BLIND_INDEX_PEPPER", None) or f"blindindex:{settings.SECRET_KEY}"
    return hashlib.sha256(pepper.encode()).digest()


def blind_index(value: str | None, *, normalise: str = "upper") -> str | None:
    """HMAC-SHA256 hex of ``value`` after normalisation (``upper``/``lower``/``none``).

    Returns ``None`` for empty input so a NULL column stays NULL.
    """
    if value is None:
        return None
    text = value.strip().replace(" ", "")
    if not text:
        return None
    if normalise == "upper":
        text = text.upper()
    elif normalise == "lower":
        text = text.lower()
    import hmac as _hmac

    return _hmac.new(_blind_index_pepper(), text.encode(), hashlib.sha256).hexdigest()


class BlindIndex:
    """Namespaced blind-index helpers, one per searchable field kind."""

    @staticmethod
    def pan(value: str | None) -> str | None:
        return blind_index(value, normalise="upper")

    @staticmethod
    def gstin(value: str | None) -> str | None:
        return blind_index(value, normalise="upper")

    @staticmethod
    def email(value: str | None) -> str | None:
        return blind_index(value, normalise="lower")
