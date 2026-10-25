"""Privacy-programme settings with safe defaults.

Every value is read from ``app.core.config.settings`` when the field exists
there and falls back to the default below otherwise, so the module runs (and
its tests pass) before the operator adds the fields to ``Settings``. The
matching ``VS_*`` environment variables are listed in docs/PRIVACY_NOTICE.md.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings

_DEFAULTS: dict[str, Any] = {
    # Versions the user/client accepted — bump when the text changes.
    "CURRENT_TERMS_VERSION": "2026-09-27",
    "CURRENT_PRIVACY_NOTICE_VERSION": "2026-10-25",
    # DPDP s.8(9): the person a Data Principal may contact.
    "GRIEVANCE_OFFICER_NAME": "Salil Shaida",
    "GRIEVANCE_OFFICER_EMAIL": "grievance@vidhisangh.com",
    "GRIEVANCE_OFFICER_ADDRESS": "VidhiSangh, India",
    # Legal hold on client erasure: matters closed within this many years
    # block hard deletion (Limitation Act 1963 / Bar Council record-keeping
    # practice for advocates' files).
    "LEGAL_HOLD_YEARS": 8,
    # A cancelled tenant is erased by the retention job after this grace period.
    "TENANT_ERASE_GRACE_DAYS": 30,
    # Retention schedule (days) applied by app.scripts.retention_purge.
    "DATA_RETENTION_DAYS_DELIVERIES": 90,
    "DATA_RETENTION_DAYS_NOTIFICATIONS": 365,
    "DATA_RETENTION_DAYS_REVOKED_TOKENS": 30,
    "DATA_RETENTION_DAYS_DELETED_DOCUMENTS": 30,
    "DATA_RETENTION_DAYS_DELETED_DRAFTS": 30,
    "DATA_RETENTION_DAYS_OAUTH_STATES": 1,
    # Response SLA for rights requests (days) — used for due_at.
    "PRIVACY_REQUEST_SLA_DAYS": 30,
}


def privacy_setting(name: str) -> Any:
    if name not in _DEFAULTS:
        raise KeyError(name)
    value = getattr(settings, name, None)
    return _DEFAULTS[name] if value in (None, "") else value
