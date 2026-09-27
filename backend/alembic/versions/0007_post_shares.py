"""Post shares (reposts): a ``share_count`` plus a frozen snapshot of the
original post carried on the repost (denormalised — no join needed to render).

Global cross-tenant social layer — no tenant_id scoping, no RLS.

Revision ID: 0007_shares
Revises: 0006_bookmarks
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_shares"
down_revision: str | None = "0006_bookmarks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.add_column("posts", sa.Column("share_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("posts", sa.Column("shared_from_id", UUID, nullable=True))
    op.add_column("posts", sa.Column("shared_author_name", sa.String(200), nullable=True))
    op.add_column("posts", sa.Column("shared_author_avatar_url", sa.String(500), nullable=True))
    op.add_column("posts", sa.Column("shared_content", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("shared_created_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_posts_shared_from_id", "posts", ["shared_from_id"])


def downgrade() -> None:
    op.drop_index("ix_posts_shared_from_id", table_name="posts")
    op.drop_column("posts", "shared_created_at")
    op.drop_column("posts", "shared_content")
    op.drop_column("posts", "shared_author_avatar_url")
    op.drop_column("posts", "shared_author_name")
    op.drop_column("posts", "shared_from_id")
    op.drop_column("posts", "share_count")
