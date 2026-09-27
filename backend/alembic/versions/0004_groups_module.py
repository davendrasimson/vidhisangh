"""Groups module: groups / communities / firm pages, memberships, community
posts and post likes.

Like the professional network, these are the cross-tenant social layer, so —
unlike practice-management tables — they are intentionally global (no tenant_id
scoping, no RLS). A firm-page group records its owning ``tenant_id`` for
reference only.

Revision ID: 0004_groups
Revises: 0003_network
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_groups"
down_revision: str | None = "0003_network"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("group_type", sa.String(20), nullable=False, server_default="community"),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="public"),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("cover_url", sa.String(500), nullable=True),
        sa.Column("owner_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("post_count", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.UniqueConstraint("slug", name="groups_slug"),
    )
    op.create_index("ix_groups_slug", "groups", ["slug"])
    op.create_index("ix_groups_group_type", "groups", ["group_type"])
    op.create_index("ix_groups_owner_id", "groups", ["owner_id"])

    op.create_table(
        "group_memberships",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("group_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("member_name", sa.String(200), nullable=False),
        sa.Column("member_headline", sa.String(200), nullable=True),
        sa.Column("member_avatar_url", sa.String(500), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("group_id", "user_id", name="group_membership_unique"),
    )
    op.create_index("ix_group_memberships_group_id", "group_memberships", ["group_id"])
    op.create_index("ix_group_memberships_user_id", "group_memberships", ["user_id"])
    op.create_index("ix_group_memberships_status", "group_memberships", ["status"])

    op.create_table(
        "group_posts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("group_id", UUID, nullable=False),
        sa.Column("author_id", UUID, nullable=False),
        sa.Column("author_name", sa.String(200), nullable=False),
        sa.Column("author_avatar_url", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_group_posts_group_id", "group_posts", ["group_id"])
    op.create_index("ix_group_posts_author_id", "group_posts", ["author_id"])

    op.create_table(
        "group_post_likes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("group_post_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["group_post_id"], ["group_posts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("group_post_id", "user_id", name="group_post_like_unique"),
    )
    op.create_index("ix_group_post_likes_group_post_id", "group_post_likes", ["group_post_id"])
    op.create_index("ix_group_post_likes_user_id", "group_post_likes", ["user_id"])


def downgrade() -> None:
    op.drop_table("group_post_likes")
    op.drop_table("group_posts")
    op.drop_table("group_memberships")
    op.drop_table("groups")
