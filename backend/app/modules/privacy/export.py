"""Row → JSON helpers shared by the user, client and tenant exports."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import inspect

# Column names that are secrets or derived indexes — never exported.
SECRET_COLUMNS: frozenset[str] = frozenset({
    "hashed_password", "mfa_secret", "token_hash", "code_hash", "key_hash", "token",
    "public_key", "code_verifier", "nonce", "challenge", "pan_bidx", "gstin_bidx", "email_bidx",
    "device_fingerprint",
})


def jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value


def row_dict(obj: Any, *, only: Iterable[str] | None = None, exclude: Iterable[str] = ()) -> dict[str, Any]:
    """Serialise an ORM instance's column attributes (no relationships)."""
    keys = [attr.key for attr in inspect(obj).mapper.column_attrs]
    wanted = set(only) if only else None
    skip = SECRET_COLUMNS | set(exclude)
    return {
        k: jsonable(getattr(obj, k))
        for k in keys
        if k not in skip and (wanted is None or k in wanted)
    }
