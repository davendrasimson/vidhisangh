"""Post bookmarks: a user's private saved posts.

Global cross-tenant social layer — no tenant_id scoping, no RLS.

Revision ID: 0006_bookmarks
Revises: 0005_group_comments
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_bookmarks"
down_revision: str | None = "0005_group_comments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "post_bookmarks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("post_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("post_id", "user_id", name="bookmark_unique"),
    )
    op.create_index("ix_post_bookmarks_post_id", "post_bookmarks", ["post_id"])
    op.create_index("ix_post_bookmarks_user_id", "post_bookmarks", ["user_id"])


def downgrade() -> None:
    op.drop_table("post_bookmarks")
