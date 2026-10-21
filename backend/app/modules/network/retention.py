"""Retention for feed photos: uploads never posted, and photos of deleted posts.

A photo uploaded in the composer but never posted is removed after a day; a
deleted post's photos after 30 days (time to restore a mistaken delete).
Rows go first, then the stored bytes — and the bytes only on a real run
(``app.scripts.retention_purge`` sets ``DRY_RUN`` for ``--dry-run``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.retention import DRY_RUN
from app.core.storage import get_storage
from app.modules.network.models import Post, PostImage

log = structlog.get_logger("app.retention.post_images")
UNUSED_AFTER = timedelta(days=1)
DELETED_POST_AFTER = timedelta(days=30)


async def purge_post_images(session: AsyncSession, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    from app.modules.groups.models import GroupPost

    deleted_posts = select(Post.id).where(Post.deleted_at.is_not(None), Post.deleted_at < now - DELETED_POST_AFTER)
    deleted_group_posts = select(GroupPost.id).where(
        GroupPost.deleted_at.is_not(None), GroupPost.deleted_at < now - DELETED_POST_AFTER)
    images = (await session.scalars(select(PostImage).where(or_(
        PostImage.post_id.is_(None) & PostImage.group_post_id.is_(None) & (PostImage.created_at < now - UNUSED_AFTER),
        PostImage.post_id.in_(deleted_posts),
        PostImage.group_post_id.in_(deleted_group_posts),
    )))).all()
    keys = [i.storage_key for i in images]
    for image in images:
        await session.delete(image)
    await session.flush()
    if keys and not DRY_RUN.get():
        await session.commit()  # rows gone before the bytes, so nothing points at a missing file
        storage = get_storage()
        for key in keys:
            try:
                await storage.delete(key)
            except Exception as exc:  # noqa: BLE001 - a missing object is not a failure
                log.warning("post_image_delete_failed", error=type(exc).__name__)
    return len(keys)
