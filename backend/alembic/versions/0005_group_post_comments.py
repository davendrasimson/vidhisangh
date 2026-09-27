"""Group post comments: a ``comment_count`` on group posts and a
``group_post_comments`` table (flat comments on a community post).

Global cross-tenant social layer — no tenant_id scoping, no RLS.

Revision ID: 0005_group_comments
Revises: 0004_groups
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_group_comments"
down_revision: str | None = "0004_groups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "group_posts",
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "group_post_comments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("group_post_id", UUID, nullable=False),
        sa.Column("author_id", UUID, nullable=False),
        sa.Column("author_name", sa.String(200), nullable=False),
        sa.Column("author_avatar_url", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["group_post_id"], ["group_posts.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_group_post_comments_group_post_id", "group_post_comments", ["group_post_id"]
    )
    op.create_index(
        "ix_group_post_comments_author_id", "group_post_comments", ["author_id"]
    )


def downgrade() -> None:
    op.drop_table("group_post_comments")
    op.drop_column("group_posts", "comment_count")
