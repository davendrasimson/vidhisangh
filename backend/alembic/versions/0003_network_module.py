"""Professional network module: global directory, connections, follows, posts,
reactions and comments.

These tables form the cross-tenant social layer, so — unlike practice-management
tables — they are intentionally global (no tenant_id scoping, no RLS).

Revision ID: 0003_network
Revises: 0002_profile
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_network"
down_revision: str | None = "0002_profile"
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
        "network_identities",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("headline", sa.String(200), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.UniqueConstraint("user_id", name="network_identities_user"),
    )
    op.create_index("ix_network_identities_user_id", "network_identities", ["user_id"])
    op.create_index("ix_network_identities_tenant_id", "network_identities", ["tenant_id"])

    op.create_table(
        "connections",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("requester_id", UUID, nullable=False),
        sa.Column("addressee_id", UUID, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("message", sa.String(300), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("requester_id", "addressee_id", name="connection_pair"),
    )
    op.create_index("ix_connections_requester_id", "connections", ["requester_id"])
    op.create_index("ix_connections_addressee_id", "connections", ["addressee_id"])
    op.create_index("ix_connections_status", "connections", ["status"])

    op.create_table(
        "follows",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("follower_id", UUID, nullable=False),
        sa.Column("followee_id", UUID, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("follower_id", "followee_id", name="follow_pair"),
    )
    op.create_index("ix_follows_follower_id", "follows", ["follower_id"])
    op.create_index("ix_follows_followee_id", "follows", ["followee_id"])

    op.create_table(
        "posts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("author_id", UUID, nullable=False),
        sa.Column("author_name", sa.String(200), nullable=False),
        sa.Column("author_headline", sa.String(200), nullable=True),
        sa.Column("author_avatar_url", sa.String(500), nullable=True),
        sa.Column("post_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="public"),
        sa.Column("hashtags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.create_index("ix_posts_author_id", "posts", ["author_id"])
    op.create_index("ix_posts_visibility", "posts", ["visibility"])
    op.create_index("ix_posts_created_at", "posts", ["created_at"])

    op.create_table(
        "post_reactions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("post_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("reaction", sa.String(20), nullable=False, server_default="like"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("post_id", "user_id", name="reaction_unique"),
    )
    op.create_index("ix_post_reactions_post_id", "post_reactions", ["post_id"])
    op.create_index("ix_post_reactions_user_id", "post_reactions", ["user_id"])

    op.create_table(
        "post_comments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("post_id", UUID, nullable=False),
        sa.Column("parent_id", UUID, nullable=True),
        sa.Column("author_id", UUID, nullable=False),
        sa.Column("author_name", sa.String(200), nullable=False),
        sa.Column("author_avatar_url", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["post_comments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_post_comments_post_id", "post_comments", ["post_id"])
    op.create_index("ix_post_comments_author_id", "post_comments", ["author_id"])


def downgrade() -> None:
    op.drop_table("post_comments")
    op.drop_table("post_reactions")
    op.drop_table("posts")
    op.drop_table("follows")
    op.drop_table("connections")
    op.drop_table("network_identities")
