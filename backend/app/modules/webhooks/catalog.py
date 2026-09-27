"""The catalog of webhook event types tenants can subscribe to.

Keep keys stable — they are the contract receivers filter on. ``ping`` is the
built-in test event emitted by the "send test" endpoint.
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
]

EVENT_KEYS: set[str] = {e.key for e in EVENT_CATALOG}
