"""Post mentions: users tagged (@mentioned) in a post, with a denormalised
name snapshot for rendering.

Global cross-tenant social layer — no tenant_id scoping, no RLS.

Revision ID: 0008_mentions
Revises: 0007_shares
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_mentions"
down_revision: str | None = "0007_shares"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "post_mentions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("post_id", UUID, nullable=False),
        sa.Column("mentioned_user_id", UUID, nullable=False),
        sa.Column("mentioned_name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("post_id", "mentioned_user_id", name="mention_unique"),
    )
    op.create_index("ix_post_mentions_post_id", "post_mentions", ["post_id"])
    op.create_index("ix_post_mentions_mentioned_user_id", "post_mentions", ["mentioned_user_id"])


def downgrade() -> None:
    op.drop_table("post_mentions")
