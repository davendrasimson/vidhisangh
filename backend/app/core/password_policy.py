"""Password policy: length + character classes + a local breached/common-password
deny-list (audit A-34).

The minimum length stays at ``settings.PASSWORD_MIN_LENGTH`` (a product
decision); what this adds is a check against the most common passwords, so
``Password@123`` no longer satisfies "upper, lower, digit, symbol".

The list ships in ``app/core/data/common_passwords.txt`` (one per line, lower
case, ``#`` comments). Matching is case-insensitive and also applied to the
candidate with its trailing digits/symbols stripped, which catches the usual
``Welcome@2026`` / ``Admin123!`` dressings of a common base word.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

_DATA_FILE = Path(__file__).with_name("data") / "common_passwords.txt"
_TRAILING = re.compile(r"[\d\W_]+$")
_LEADING = re.compile(r"^[\d\W_]+")

RULES_MESSAGE = (
    "Password must be at least "
    f"{settings.PASSWORD_MIN_LENGTH} characters and include upper- and "
    "lower-case letters, a digit, and a symbol."
)
COMMON_MESSAGE = (
    "This password is too common or appears in breached-password lists. "
    "Choose something less guessable."
)

_LEET = str.maketrans({"@": "a", "0": "o", "1": "i", "!": "i", "3": "e", "$": "s", "5": "s", "4": "a", "7": "t"})


@lru_cache
def common_passwords() -> frozenset[str]:
    try:
        lines = _DATA_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:  # pragma: no cover - packaging problem, do not block sign-up
        return frozenset()
    return frozenset(
        line.strip().lower() for line in lines if line.strip() and not line.startswith("#")
    )


def _variants(value: str) -> set[str]:
    lowered = value.lower()
    out = {lowered}
    stripped = _TRAILING.sub("", lowered)
    out.add(stripped)
    out.add(_LEADING.sub("", stripped))
    out.add(lowered.translate(_LEET))
    out.add(stripped.translate(_LEET))
    return {v for v in out if v}


def is_common_password(value: str) -> bool:
    deny = common_passwords()
    return any(v in deny for v in _variants(value))


class PasswordPolicy:
    """Validates a candidate password; raises ``ValueError`` with a user message."""

    @staticmethod
    def validate(value: str, *, email: str | None = None) -> str:
        if len(value) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(RULES_MESSAGE)
        checks = [
            re.search(r"[a-z]", value),
            re.search(r"[A-Z]", value),
            re.search(r"\d", value),
            re.search(r"[^\w\s]", value),
        ]
        if not all(checks):
            raise ValueError(RULES_MESSAGE)
        if is_common_password(value):
            raise ValueError(COMMON_MESSAGE)
        if email:
            local = email.split("@", 1)[0].lower()
            if len(local) >= 4 and local in value.lower():
                raise ValueError("Password must not contain your email address.")
        return value


validate_password = PasswordPolicy.validate
