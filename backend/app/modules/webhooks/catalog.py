"""The catalog of webhook event types tenants can subscribe to.

Keep keys stable — they are the contract receivers filter on. ``ping`` is the
built-in test event emitted by the "send test" endpoint.

``security.*`` events (audit A-20) let a tenant stream account-security signals
to its SIEM; they are emitted through ``emit_security_event`` in the service.
"""

from __future__ import annotations

from typing import NamedTuple


class EventDef(NamedTuple):
    key: str
    description: str


EVENT_CATALOG: list[EventDef] = [
    EventDef("ping", "Test event sent from the webhook settings screen."),
    EventDef("matter.created", "A new matter/case was opened."),
    EventDef("invoice.paid", "An invoice was fully paid."),
    EventDef("lead.won", "A CRM lead was marked won."),
    EventDef("user.created", "A user was added to the organisation."),
    EventDef("webhook.auto_disabled", "A webhook endpoint was disabled after repeated delivery failures."),
    EventDef("security.lockout", "An account was locked after too many failed sign-in attempts."),
    EventDef("security.refresh_reuse", "A revoked refresh token was presented again (possible token theft)."),
    EventDef("security.mfa_disabled", "Multi-factor authentication was switched off for an account."),
]

EVENT_KEYS: set[str] = {e.key for e in EVENT_CATALOG}
SECURITY_EVENT_KEYS: set[str] = {k for k in EVENT_KEYS if k.startswith("security.")}
