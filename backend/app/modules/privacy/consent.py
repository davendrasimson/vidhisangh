"""Consent ledger helpers shared by the clients module and the channel gates.

Rules (DPDP s.6):
- Consent is recorded per *purpose* as an append-only event; a withdrawal is a
  new ``granted=False`` event and never deletes the original grant.
- The ``consent_*`` booleans on ``clients`` are a cache derived from the
  latest event per purpose — staff edits never change them without an event.
- Client-facing sends check the latest event for the channel's purpose.
  Messages that are necessary for the engagement itself (the KYC link) are
  sent on the basis of the contract and record that basis instead.
"""

from __future__ import annotations

import hashlib
import ipaddress
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.privacy.models import (
    CONSENT_FLAG_PURPOSES,
    ClientConsentEvent,
    ConsentPurpose,
    ConsentSource,
)

if TYPE_CHECKING:  # avoid an import cycle: clients.service imports this module
    from app.modules.clients.models import Client

# Channel → the purpose whose latest consent gates it.
CHANNEL_PURPOSES: dict[str, ConsentPurpose] = {
    "email": ConsentPurpose.CONTACT_EMAIL,
    "sms": ConsentPurpose.CONTACT_SMS,
    "whatsapp": ConsentPurpose.CONTACT_WHATSAPP,
}


def coarse_ip(ip: str | None) -> str | None:
    """Reduce an address to ``<network>/24#<sha256 prefix>`` (``/48`` for IPv6).

    Enough to detect abuse patterns and prove a submission came from one
    network; not enough to identify a device. The raw address is never stored.
    """
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return "invalid#" + hashlib.sha256(ip.encode()).hexdigest()[:12]
    prefix = 24 if addr.version == 4 else 48
    net = ipaddress.ip_network(f"{addr}/{prefix}", strict=False)
    digest = hashlib.sha256(str(addr).encode()).hexdigest()[:12]
    return f"{net}#{digest}"


def record_consent_event(
    session: AsyncSession,
    *,
    client: Client,
    purpose: ConsentPurpose,
    granted: bool,
    source: ConsentSource | str,
    actor_id: uuid.UUID | None,
    notice_version: str | None = None,
    ip: str | None = None,
    ip_coarse: str | None = None,
    note: str | None = None,
    recorded_at: datetime | None = None,
) -> ClientConsentEvent:
    """Append one event and refresh the cached flag on the client.

    ``ip`` is coarsened here; ``ip_coarse`` is for callers that already hold
    the coarse form (a KYC submission recorded earlier).
    """
    now = recorded_at or datetime.now(UTC)
    event = ClientConsentEvent(
        tenant_id=client.tenant_id,
        client_id=client.id,
        purpose=purpose,
        granted=granted,
        source=ConsentSource(source),
        notice_version=notice_version,
        actor_id=actor_id,
        recorded_at=now,
        ip_coarse=ip_coarse or coarse_ip(ip),
        note=note,
    )
    session.add(event)
    apply_event_to_cache(client, event)
    return event


def apply_event_to_cache(client: Client, event: ClientConsentEvent) -> None:
    for flag, purpose in CONSENT_FLAG_PURPOSES.items():
        if purpose == event.purpose:
            setattr(client, flag, event.granted)
            client.consent_recorded_at = event.recorded_at
            client.consent_source = str(event.source)
    if event.purpose == ConsentPurpose.GUARDIAN_CONSENT:
        client.guardian_consent_recorded_at = event.recorded_at if event.granted else None


def record_flag_changes(
    session: AsyncSession,
    *,
    client: Client,
    values: dict,
    source: ConsentSource | str,
    actor_id: uuid.UUID | None,
    notice_version: str | None = None,
    ip: str | None = None,
    ip_coarse: str | None = None,
    only_changes: bool = True,
) -> list[ClientConsentEvent]:
    """Translate ``consent_*`` booleans in an edit/submission into events.

    With ``only_changes`` a value equal to the cached flag produces no event
    (a staff re-save is not a fresh consent); the KYC form passes ``False`` so
    every explicit answer the client gave is on record, ticked or not.
    """
    events: list[ClientConsentEvent] = []
    for flag, purpose in CONSENT_FLAG_PURPOSES.items():
        if flag not in values or values[flag] is None:
            continue
        wanted = bool(values[flag])
        if only_changes and wanted == bool(getattr(client, flag)):
            continue
        events.append(
            record_consent_event(
                session, client=client, purpose=purpose, granted=wanted, source=source,
                actor_id=actor_id, notice_version=notice_version, ip=ip, ip_coarse=ip_coarse,
            )
        )
    return events


async def latest_consent(
    session: AsyncSession, client_id: uuid.UUID, purpose: ConsentPurpose
) -> ClientConsentEvent | None:
    res = await session.execute(
        select(ClientConsentEvent)
        .where(ClientConsentEvent.client_id == client_id, ClientConsentEvent.purpose == purpose)
        .order_by(ClientConsentEvent.recorded_at.desc(), ClientConsentEvent.created_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def client_channel_allowed(session: AsyncSession, client_id: uuid.UUID, channel: str) -> bool:
    """True when the client's latest consent for the channel's purpose is a grant."""
    purpose = CHANNEL_PURPOSES.get(str(channel))
    if purpose is None:
        return False
    event = await latest_consent(session, client_id, purpose)
    return bool(event and event.granted)


async def consent_history(session: AsyncSession, tenant_id: uuid.UUID, client_id: uuid.UUID) -> list[ClientConsentEvent]:
    res = await session.execute(
        select(ClientConsentEvent)
        .where(ClientConsentEvent.tenant_id == tenant_id, ClientConsentEvent.client_id == client_id)
        .order_by(ClientConsentEvent.recorded_at.desc(), ClientConsentEvent.created_at.desc())
    )
    return list(res.scalars().all())
