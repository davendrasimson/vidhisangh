"""Feed photos never posted, or of long-deleted posts, are removed with their bytes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.network.models import Post, PostImage
from app.modules.network.retention import DRY_RUN, purge_post_images

pytestmark = pytest.mark.asyncio


class Store:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


async def test_unused_and_deleted_post_photos_are_purged(session_factory, monkeypatch) -> None:
    store = Store()
    monkeypatch.setattr("app.modules.network.retention.get_storage", lambda: store)
    now = datetime.now(UTC)
    author = uuid.uuid4()
    async with session_factory() as s:
        live = Post(author_id=author, author_name="A", content="live")
        gone = Post(author_id=author, author_name="A", content="gone", deleted_at=now - timedelta(days=40))
        recent_gone = Post(author_id=author, author_name="A", content="recent", deleted_at=now - timedelta(days=2))
        s.add_all([live, gone, recent_gone])
        await s.flush()

        def img(key, post=None, age=timedelta(0)):
            return PostImage(uploader_id=author, post_id=post.id if post else None, storage_key=key, content_type="image/jpeg",
                             size_bytes=1, width=1, height=1, created_at=now - age)
        s.add_all([img("unused-old", age=timedelta(days=2)), img("unused-new", age=timedelta(hours=2)),
                   img("live", live), img("gone", gone), img("recent-gone", recent_gone)])
        await s.commit()

    async with session_factory() as s:
        DRY_RUN.set(True)
        assert await purge_post_images(s, now) == 2
        await s.rollback()
        DRY_RUN.set(False)
    assert store.deleted == []  # a dry run never deletes files

    async with session_factory() as s:
        assert await purge_post_images(s, now) == 2
        await s.commit()
        left = sorted(i.storage_key for i in await s.scalars(select(PostImage)))
    assert sorted(store.deleted) == ["gone", "unused-old"]
    assert left == ["live", "recent-gone", "unused-new"]
