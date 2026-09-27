"""Application-layer field encryption for PII / secrets at rest.

Provides envelope-style symmetric encryption and a SQLAlchemy ``TypeDecorator``
so sensitive columns (MFA secrets, tokens, PII) are encrypted transparently
before they touch the database.

In production the data-encryption key should come from a managed KMS/HSM
(AWS KMS, Azure Key Vault, GCP KMS, Vault Transit). Here it is derived from
``SECRET_KEY`` for local development; swap ``_load_key()`` for a KMS call to
enable key rotation without code changes elsewhere.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, TypeDecorator

from app.core.config import settings


@lru_cache
def _load_key() -> Fernet:
    # Derive a 32-byte urlsafe key from the app secret (dev). Replace with KMS
    # data-key retrieval in production.
    digest = hashlib.sha256(f"fieldcrypt:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _load_key().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _load_key().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - defensive
        raise ValueError("Failed to decrypt field (key mismatch or corruption).") from exc


class EncryptedString(TypeDecorator):
    """Transparently encrypt/decrypt a text column at the ORM boundary."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        return encrypt(value) if value is not None else None

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        return decrypt(value) if value is not None else None
