"""Retention purges (DPDP s.8(7), audit P-1 / P-14).

Each coroutine takes a bypass-RLS session and returns the number of rows (or
objects) removed. They are registered in ``app.scripts.retention_purge.PURGES``
and are idempotent: a second run finds nothing to do. Periods come from
``app.modules.privacy.config`` (``VS_DATA_RETENTION_DAYS_*``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage
from app.db.base_class import Base
from app.modules.documents.models import Document, DocumentVersion
from app.modules.drafting.models import Draft, DraftTemplate, DraftVersion
from app.modules.identity.models import MfaBackupCode, OAuthState, RefreshToken, User, WebAuthnChallenge
from app.modules.messaging.models import ConversationParticipant, Message
from app.modules.network.models import Comment, Post, PostMention
from app.modules.notifications.models import Notification, NotificationDelivery, NotificationPreference
from app.modules.privacy.config import privacy_setting
from app.modules.tenancy.models import Tenant, TenantStatus

log = structlog.get_logger("app.retention")
DELETED_USER_NAME = "Deleted user"


def _ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def _exec(session: AsyncSession, stmt):  # noqa: ANN001, ANN202
    """Bulk DML without in-session "evaluate" sync (objects loaded from SQLite
    carry naive datetimes that cannot be compared with the aware cutoffs)."""
    return await session.execute(stmt, execution_options={"synchronize_session": False})


async def _delete_storage_keys(keys: list[str]) -> int:
    if not keys:
        return 0
    storage = get_storage()
    removed = 0
    for key in keys:
        try:
            await storage.delete(key)
            removed += 1
        except Exception as exc:  # noqa: BLE001 — a missing object is fine; keep sweeping
            log.warning("storage_delete_failed", key=key, error=type(exc).__name__)
    return removed


async def purge_oauth_states(session: AsyncSession) -> int:
    """OAuth CSRF/PKCE state: expired more than N days ago (default 1)."""
    cutoff = _ago(int(privacy_setting("DATA_RETENTION_DAYS_OAUTH_STATES")))
    res = await _exec(session, delete(OAuthState).where(OAuthState.expires_at < cutoff))
    return int(res.rowcount or 0)


async def purge_webauthn_challenges(session: AsyncSession) -> int:
    """Passkey ceremony challenges: expired."""
    res = await _exec(session, delete(WebAuthnChallenge).where(WebAuthnChallenge.expires_at < datetime.now(UTC)))
    return int(res.rowcount or 0)


async def purge_refresh_tokens(session: AsyncSession) -> int:
    """Sessions: strip IP/user-agent from every revoked token, delete tokens
    expired or revoked more than N days ago (default 30)."""
    cutoff = _ago(int(privacy_setting("DATA_RETENTION_DAYS_REVOKED_TOKENS")))
    await _exec(
        session,
        update(RefreshToken).where(RefreshToken.revoked_at.is_not(None)).values(ip_address=None, user_agent=None),
    )
    res = await _exec(
        session, delete(RefreshToken).where(or_(RefreshToken.expires_at < cutoff, RefreshToken.revoked_at < cutoff))
    )
    return int(res.rowcount or 0)


async def purge_used_backup_codes(session: AsyncSession) -> int:
    """MFA backup codes that have been used are worthless — drop the hashes."""
    res = await _exec(session, delete(MfaBackupCode).where(MfaBackupCode.used_at.is_not(None)))
    return int(res.rowcount or 0)


async def purge_deleted_documents(session: AsyncSession) -> int:
    """Documents soft-deleted more than N days ago: delete every version's
    bytes from the object store, then the rows."""
    cutoff = _ago(int(privacy_setting("DATA_RETENTION_DAYS_DELETED_DOCUMENTS")))
    doc_ids = list((await session.execute(select(Document.id).where(Document.deleted_at < cutoff))).scalars().all())
    if not doc_ids:
        return 0
    keys = list((await session.execute(
        select(DocumentVersion.storage_key).where(DocumentVersion.document_id.in_(doc_ids))
    )).scalars().all())
    await _delete_storage_keys(keys)
    await _exec(session, delete(DocumentVersion).where(DocumentVersion.document_id.in_(doc_ids)))
    res = await _exec(session, delete(Document).where(Document.id.in_(doc_ids)))
    return int(res.rowcount or 0)


async def purge_deleted_drafts(session: AsyncSession) -> int:
    """Drafts soft-deleted more than N days ago, with their snapshots."""
    cutoff = _ago(int(privacy_setting("DATA_RETENTION_DAYS_DELETED_DRAFTS")))
    ids = list((await session.execute(select(Draft.id).where(Draft.deleted_at < cutoff))).scalars().all())
    if not ids:
        return 0
    await _exec(session, delete(DraftVersion).where(DraftVersion.draft_id.in_(ids)))
    res = await _exec(session, delete(Draft).where(Draft.id.in_(ids)))
    return int(res.rowcount or 0)


async def purge_notifications(session: AsyncSession) -> int:
    """In-app notifications older than N days (default 365)."""
    cutoff = _ago(int(privacy_setting("DATA_RETENTION_DAYS_NOTIFICATIONS")))
    res = await _exec(session, delete(Notification).where(Notification.created_at < cutoff))
    return int(res.rowcount or 0)


async def erase_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, int]:
    """Cascade-delete everything a tenant holds (used by the purge and tests).

    Order: document bytes → every tenant-scoped table (reverse dependency
    order, so it also works where FKs are not enforced) → global rows that
    belong to the tenant's users → the tenant row.
    """
    counts: dict[str, int] = {}
    document_keys = list(
        (
            await session.execute(
                select(DocumentVersion.storage_key).where(DocumentVersion.tenant_id == tenant_id)
            )
        )
        .scalars()
        .all()
    )
    template_keys = list(
        (
            await session.execute(
                select(DraftTemplate.source_storage_key).where(
                    DraftTemplate.tenant_id == tenant_id
                )
            )
        )
        .scalars()
        .all()
    )
    keys = document_keys + template_keys
    counts["storage_objects"] = await _delete_storage_keys(keys)
    user_ids = list((await session.execute(select(User.id).where(User.tenant_id == tenant_id))).scalars().all())
    if user_ids:
        anon = {"author_name": DELETED_USER_NAME, "author_avatar_url": None}
        await _exec(session, update(Post).where(Post.author_id.in_(user_ids)).values(author_headline=None, **anon))
        await _exec(session, update(Comment).where(Comment.author_id.in_(user_ids)).values(**anon))
        await _exec(session, update(PostMention).where(PostMention.mentioned_user_id.in_(user_ids)).values(mentioned_name=DELETED_USER_NAME))
        await _exec(session, update(Message).where(Message.sender_id.in_(user_ids)).values(sender_name=DELETED_USER_NAME, sender_avatar_url=None))
        await _exec(session, update(ConversationParticipant).where(ConversationParticipant.user_id.in_(user_ids))
                              .values(participant_name=DELETED_USER_NAME, participant_avatar_url=None))
        for model in (Notification, NotificationPreference, NotificationDelivery):
            await _exec(session, delete(model).where(model.user_id.in_(user_ids)))
    # The audit log is append-only (trigger + REVOKE DELETE on the app role).
    # A sanctioned erasure flags the transaction and lets the tenants FK cascade
    # remove the rows (RI actions run as the table owner); a direct DELETE by
    # the app role would be refused, so audit_events is skipped in the loop.
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        await session.execute(text("SET LOCAL app.audit_purge = 'on'"))
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in ("tenants", "audit_events") or "tenant_id" not in table.c:
            continue
        res = await _exec(session, delete(table).where(table.c.tenant_id == tenant_id))
        if res.rowcount:
            counts[table.name] = int(res.rowcount)
    await _exec(session, delete(Tenant).where(Tenant.id == tenant_id))
    counts["tenants"] = 1
    return counts


async def purge_cancelled_tenants(session: AsyncSession) -> int:
    """Tenants cancelled whose grace period (``erase_after``) has passed."""
    due = list((await session.execute(
        select(Tenant.id).where(Tenant.status == TenantStatus.CANCELLED, Tenant.erase_after.is_not(None),
                                Tenant.erase_after < datetime.now(UTC))
    )).scalars().all())
    for tid in due:
        counts = await erase_tenant(session, tid)
        log.info("tenant_erased", tenant_id=str(tid), rows=sum(counts.values()))
    return len(due)


PRIVACY_PURGES = [
    purge_oauth_states,
    purge_webauthn_challenges,
    purge_refresh_tokens,
    purge_used_backup_codes,
    purge_deleted_documents,
    purge_deleted_drafts,
    purge_notifications,
    purge_cancelled_tenants,
]
